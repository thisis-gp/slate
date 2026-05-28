from __future__ import annotations
import aiosqlite
from slate.jira.client import JiraClient
from slate.jira.mapping import resolve_state_map, find_transition_id, format_worklog_started
from slate.db.queries import (
    get_jira_config, list_tasks_with_jira, insert_jira_sync_log, get_unsynced_runs,
)


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
        "worklogs": await _sync_worklogs(db, client, task["id"], jira_key),
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


async def _sync_worklogs(db, client: JiraClient, task_id: str, jira_key: str) -> dict:
    runs = await get_unsynced_runs(db, task_id, jira_key)
    synced = 0
    for run in runs:
        started_ts = run.get("started_at") or run.get("completed_at") or 0.0
        ended_ts = run.get("completed_at") or started_ts
        time_spent = max(60, int(ended_ts - started_ts))
        comment = f"[{run['tool']}] {run['agent_name']}: {run['summary'][:500]}"
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
