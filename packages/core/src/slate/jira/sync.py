from __future__ import annotations
import asyncio
import json
import uuid
import aiosqlite
from slate.jira.client import JiraClient
from slate.jira.mapping import (
    resolve_state_map, find_transition_id, format_worklog_started, is_allowed_jira_key,
)
from slate.llm.summarize import summarize_worklog
from slate.jira.scrub import scrub_identity
from slate.db.queries import (
    get_jira_config, list_tasks_with_jira, insert_jira_sync_log, get_unsynced_runs,
    get_unsynced_worklogs, mark_worklog_synced, insert_notification,
    insert_pending_sync, get_pending, set_pending_status, count_unlinked_worklogs,
    get_unsynced_worklogs_by_ids,
)
from collections import defaultdict

SUMMARY_TIMEOUT_SECONDS = 8


def _fallback_summary(entries: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for entry in entries:
        entry = entry.strip()
        if entry and entry not in seen:
            seen.add(entry)
            out.append(f"- {entry}")
    return "\n".join(out[:12])


def _worklog_entries(worklogs: list[dict]) -> list[str]:
    """Collect de-duplicated worklog summaries, scrubbed of agent/tool identity.

    Scrubbing happens here so BOTH the LLM input and the deterministic fallback
    work from clean text — no banned identity token can reach Jira on any path.
    """
    entries: list[str] = []
    seen: set[str] = set()
    for worklog in worklogs:
        summary = scrub_identity((worklog.get("summary") or "").strip())
        if summary and summary not in seen:
            seen.add(summary)
            entries.append(summary)
    return entries


async def sync_all(db: aiosqlite.Connection) -> dict:
    config = await get_jira_config(db)
    if not config or not config.get("enabled"):
        return {"skipped": True, "reason": "Jira not configured or disabled"}
    client = JiraClient(
        base_url=config["base_url"],
        email=config["email"],
        api_token=config["api_token"],
    )
    state_map = resolve_state_map(config.get("state_map"))
    tasks = await list_tasks_with_jira(db)
    results = [await _sync_task(db, client, task, state_map) for task in tasks]
    return {"synced": len(results), "results": results}


async def _sync_task(db, client: JiraClient, task: dict, state_map: dict) -> dict:
    jira_key = task["jira_issue_key"]
    return {
        "task_id": task["id"],
        "jira_key": jira_key,
        "status": await _sync_status(db, client, task, state_map),
        "worklogs": await _sync_worklogs_legacy(db, client, task["id"], jira_key),
    }


async def _sync_status(db, client: JiraClient, task: dict, state_map: dict) -> dict:
    jira_key = task["jira_issue_key"]
    target_jira_status = state_map.get(task["state"])
    if not target_jira_status:
        await insert_jira_sync_log(db, task_id=task["id"], jira_key=jira_key,
            action="transition", status="skipped",
            detail=f"No Jira mapping for Slate state '{task['state']}'")
        return {"skipped": True, "reason": f"no mapping for state {task['state']}"}
    try:
        transitions = await client.get_transitions(jira_key)
        transition_id = find_transition_id(transitions, target_jira_status)
        if not transition_id:
            available = [t["to"]["name"] for t in transitions]
            await insert_jira_sync_log(db, task_id=task["id"], jira_key=jira_key,
                action="transition", status="approval_needed",
                detail=f"Transition to '{target_jira_status}' not available. Available: {available}")
            return {"skipped": True, "reason": f"transition '{target_jira_status}' not available"}
        await client.transition_issue(jira_key, transition_id)
        await insert_jira_sync_log(db, task_id=task["id"], jira_key=jira_key,
            action="transition", status="ok",
            detail=f"Transitioned to '{target_jira_status}'")
        return {"ok": True, "transitioned_to": target_jira_status}
    except Exception as e:
        await insert_jira_sync_log(db, task_id=task["id"], jira_key=jira_key,
            action="transition", status="error", detail=str(e))
        return {"error": str(e)}


async def _sync_worklogs_legacy(db, client: JiraClient, task_id: str, jira_key: str) -> dict:
    """Legacy: sync individual agent_runs as worklogs."""
    runs = await get_unsynced_runs(db, task_id, jira_key)
    synced = 0
    for run in runs:
        started_ts = run.get("started_at") or run.get("completed_at") or 0.0
        ended_ts = run.get("completed_at") or started_ts
        time_spent = max(60, int(ended_ts - started_ts))
        comment = scrub_identity(run["summary"])[:500]
        try:
            await client.add_worklog(jira_key, time_spent_seconds=time_spent,
                                      comment=comment,
                                      started=format_worklog_started(started_ts))
            await insert_jira_sync_log(db, task_id=task_id, jira_key=jira_key,
                action="worklog", status="ok",
                detail=f"Logged {time_spent}s", run_id=run["id"])
            synced += 1
        except Exception as e:
            await insert_jira_sync_log(db, task_id=task_id, jira_key=jira_key,
                action="worklog", status="error", detail=str(e), run_id=run["id"])
    return {"synced_worklogs": synced}


async def sync_worklogs_all(db: aiosqlite.Connection) -> dict:
    """New: sync all pending worklogs, aggregating by Jira issue."""
    config = await get_jira_config(db)
    if not config or not config.get("enabled"):
        return {"skipped": True, "reason": "Jira not configured or disabled"}
    client = JiraClient(
        base_url=config["base_url"],
        email=config["email"],
        api_token=config["api_token"],
    )

    logs = await get_unsynced_worklogs(db)
    if not logs:
        return {"synced": 0, "failed": 0, "details": []}

    by_jira = defaultdict(list)
    for log in logs:
        jira_key = log.get("jira_issue_key")
        if jira_key:
            by_jira[jira_key].append(log)

    synced = 0
    failed = 0
    details = []

    for jira_key, items in by_jira.items():
        total_seconds = sum(w["time_spent_seconds"] for w in items)
        total_mins = total_seconds // 60

        summaries = _worklog_entries(items)
        combined_summary = _fallback_summary(summaries)
        if len(summaries) > 10:
            combined_summary += f"\n... and {len(summaries) - 10} more entries"

        started_ts = min(w["started_at"] for w in items)

        try:
            result = await client.add_worklog(
                jira_key,
                time_spent_seconds=max(60, total_seconds),
                comment=combined_summary,
                started=format_worklog_started(started_ts),
            )
            jira_wid = result.get("id", "")

            for w in items:
                await mark_worklog_synced(db, w["id"], jira_wid)
                await insert_jira_sync_log(
                    db, task_id=w["task_id"], jira_key=jira_key,
                    action="worklog", status="ok",
                    detail=f"Aggregated {len(items)} entries, {total_mins}m",
                )

            synced += 1
            details.append({"jira_key": jira_key, "status": "ok", "entries": len(items), "minutes": total_mins})
        except Exception as e:
            failed += 1
            details.append({"jira_key": jira_key, "status": "error", "error": str(e)[:200]})
            for w in items:
                await insert_jira_sync_log(
                    db, task_id=w["task_id"], jira_key=jira_key,
                    action="worklog", status="error",
                    detail=str(e)[:200],
                )

    return {"synced": synced, "failed": failed, "details": details}


# ── Approval-gated daily sync (build → summarize → stage → approve/reject) ─────

async def build_batch(db: aiosqlite.Connection) -> dict:
    """Build a pending sync batch (DB-only, no Jira API calls).

    Groups unsynced worklogs by Jira issue and pairs each with the task's
    current/target state. Returns ``{"issues": [...]}`` (or ``skipped``).
    """
    config = await get_jira_config(db)
    if not config or not config.get("enabled"):
        return {"issues": [], "skipped": True}

    tasks = await list_tasks_with_jira(db)
    by_key_task: dict[str, dict] = {}
    for t in tasks:
        key = t.get("jira_issue_key")
        if key:
            by_key_task[key] = t

    worklogs = await get_unsynced_worklogs(db)
    by_jira: dict[str, list[dict]] = defaultdict(list)
    for w in worklogs:
        key = w.get("jira_issue_key")
        if key:
            by_jira[key].append(w)

    issues: list[dict] = []
    for jira_key, items in by_jira.items():
        # Defense in depth: never push to a non-allowed project.
        if not is_allowed_jira_key(jira_key):
            continue
        task = by_key_task.get(jira_key, {})
        current_state = task.get("state")
        total_seconds = sum(w["time_spent_seconds"] for w in items)
        entries = _worklog_entries(items)
        issues.append({
            "jira_key": jira_key,
            "task_id": task.get("id"),
            "current_state": current_state,
            "worklog_ids": [w["id"] for w in items],
            "entries": entries,
            "total_seconds": total_seconds,
            "started_ts": min(w["started_at"] for w in items),
        })

    return {"issues": issues, "unlinked_count": await count_unlinked_worklogs(db)}


async def summarize_batch(batch: dict) -> tuple[dict, str]:
    """LLM-summarize each issue's worklog entries. Returns (batch, provider)."""
    overall_provider = "concat"
    for issue in batch.get("issues", []):
        entries = issue.get("entries") or []
        if not entries:
            continue
        try:
            summary, provider = await asyncio.wait_for(
                summarize_worklog(issue["jira_key"], entries, issue["total_seconds"] // 60),
                timeout=SUMMARY_TIMEOUT_SECONDS,
            )
        except Exception:
            summary, provider = _fallback_summary(entries), "concat_timeout"
        issue["summary"] = summary
        issue["summary_provider"] = provider
        if overall_provider == "concat" and provider != "concat":
            overall_provider = provider
    return batch, overall_provider


async def prepare_pending(db: aiosqlite.Connection) -> dict:
    """Build + summarize a batch and stage it pending human approval."""
    batch = await build_batch(db)
    issues = batch.get("issues", [])
    if not issues:
        return {
            "pending_id": None,
            "reason": "nothing to sync",
            "unlinked_count": batch.get("unlinked_count", 0),
        }

    batch, provider = await summarize_batch(batch)
    pending_id = str(uuid.uuid4())
    await insert_pending_sync(
        db, id=pending_id, batch_json=json.dumps(batch), summary_provider=provider
    )

    total_mins = sum(i["total_seconds"] for i in issues) // 60
    await insert_notification(
        db,
        id=str(uuid.uuid4()),
        type="jira_sync_approval",
        title="Jira sync needs approval",
        body=f"{len(issues)} issue(s), total {total_mins}m — review & approve",
        channel="console",
    )
    return {"pending_id": pending_id, "batch": batch}


async def approve_pending(
    db: aiosqlite.Connection, pending_id: str, exclude: list[str] | None = None,
) -> dict:
    """Push an approved pending batch to Jira. NEVER called without approval."""
    exclude = exclude or []
    pending = await get_pending(db, pending_id)
    if not pending:
        return {"error": "pending batch not found"}
    if pending["status"] != "pending":
        return {"error": f"pending batch already {pending['status']}"}

    batch = json.loads(pending["batch_json"])
    config = await get_jira_config(db)
    if not config or not config.get("enabled"):
        return {"error": "Jira not configured or disabled"}
    client = JiraClient(
        base_url=config["base_url"],
        email=config["email"],
        api_token=config["api_token"],
    )

    results: list[dict] = []
    pushed = 0
    failed = 0

    for issue in batch.get("issues", []):
        jira_key = issue["jira_key"]
        task_id = issue.get("task_id")
        if jira_key in exclude:
            for wid in issue.get("worklog_ids", []):
                await mark_worklog_synced(db, wid, f"excluded:{pending_id}")
            await insert_jira_sync_log(
                db, task_id=task_id, jira_key=jira_key,
                action="worklog", status="excluded",
                detail=f"{len(issue.get('worklog_ids', []))} entries excluded by approval",
            )
            results.append({"jira_key": jira_key, "status": "excluded"})
            continue
        result: dict = {"jira_key": jira_key}
        try:
            fresh_items = await get_unsynced_worklogs_by_ids(db, issue.get("worklog_ids", []))
            entries = _worklog_entries(fresh_items)
            if not entries:
                await insert_jira_sync_log(
                    db, task_id=task_id, jira_key=jira_key,
                    action="worklog", status="skipped",
                    detail="All entries were already synced before approval",
                )
                result["status"] = "skipped"
                result["reason"] = "already synced"
                results.append(result)
                continue
            if entries:
                total_seconds = sum(w["time_spent_seconds"] for w in fresh_items)
                total_mins = total_seconds // 60
                comment = (
                    issue.get("summary") or ""
                    if len(fresh_items) == len(issue.get("worklog_ids", []))
                    else _fallback_summary(entries)
                )
                jira_result = await client.add_worklog(
                    jira_key,
                    time_spent_seconds=max(60, total_seconds),
                    comment=comment,
                    started=format_worklog_started(min(w["started_at"] for w in fresh_items)),
                )
                jira_wid = jira_result.get("id", "")
                for w in fresh_items:
                    await mark_worklog_synced(db, w["id"], jira_wid)
                await insert_jira_sync_log(
                    db, task_id=task_id, jira_key=jira_key,
                    action="worklog", status="ok",
                    detail=f"{len(entries)} entries, {total_mins}m",
                )
                result["worklog"] = {"entries": len(entries), "minutes": total_mins}

            result["status"] = "ok"
            pushed += 1
        except Exception as e:  # noqa: BLE001
            await insert_jira_sync_log(
                db, task_id=task_id, jira_key=jira_key,
                action="worklog", status="error", detail=str(e)[:200],
            )
            result["status"] = "error"
            result["error"] = str(e)[:200]
            failed += 1
        results.append(result)

    await set_pending_status(db, pending_id, "pushed", result_json=json.dumps(results))
    await _supersede_overlapping_pending_batches(db, pending_id, batch)
    return {"pushed": pushed, "failed": failed, "results": results}


async def reject_pending(db: aiosqlite.Connection, pending_id: str) -> dict:
    await set_pending_status(db, pending_id, "rejected")
    return {"rejected": True}


async def _supersede_overlapping_pending_batches(
    db: aiosqlite.Connection, approved_pending_id: str, approved_batch: dict,
) -> None:
    approved_worklog_ids = {
        wid
        for issue in approved_batch.get("issues", [])
        for wid in issue.get("worklog_ids", [])
    }
    if not approved_worklog_ids:
        return

    async with db.execute(
        "SELECT id, batch_json FROM jira_pending_sync "
        "WHERE status = 'pending' AND id <> ?",
        (approved_pending_id,),
    ) as cur:
        pending_rows = [dict(row) async for row in cur]

    for row in pending_rows:
        try:
            batch = json.loads(row["batch_json"])
        except Exception:  # noqa: BLE001
            continue
        row_worklog_ids = {
            wid
            for issue in batch.get("issues", [])
            for wid in issue.get("worklog_ids", [])
        }
        if approved_worklog_ids & row_worklog_ids:
            await set_pending_status(
                db,
                row["id"],
                "superseded",
                result_json=json.dumps({"superseded_by": approved_pending_id}),
            )
