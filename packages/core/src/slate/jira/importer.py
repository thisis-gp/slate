"""Jira → Slate import (staging only; every issue is human-approved).

Pull direction is the inverse of the rest of Slate's Jira integration, so it gets
the same guard rail: ``stage_assigned_issues`` only *stages* candidates into
``jira_pending_import`` — it never creates tasks. A human reviews the queue in the
UI, assigns each issue to a Slate project, and ``approve_import`` then creates the
linked task (and scaffolds its Obsidian doc). Already-imported keys and
already-pending keys are skipped, so re-running is idempotent.
"""
from __future__ import annotations
import json
import uuid
import aiosqlite
from slate.jira.client import JiraClient
from slate.jira.mapping import is_allowed_jira_key
from slate.db.queries import (
    get_jira_config, task_exists_for_jira_key, pending_import_exists,
    insert_pending_import, get_pending_import, set_pending_import_decided,
    insert_task, get_task, get_task_context,
)

# Default JQL: open issues currently assigned to the configured account.
DEFAULT_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"

# Jira issue type -> Slate task type.
_TYPE_MAP = {
    "bug": "bug", "story": "feature", "task": "chore", "sub-task": "chore",
    "epic": "feature", "spike": "spike", "research": "research",
}
# Jira priority -> Slate priority.
_PRIORITY_MAP = {
    "highest": "critical", "critical": "critical", "high": "high",
    "medium": "medium", "low": "low", "lowest": "low",
}


def _field(issue: dict, *path, default=None):
    cur = issue.get("fields", {})
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default


async def stage_assigned_issues(db: aiosqlite.Connection, *, jql: str = DEFAULT_JQL) -> dict:
    """Fetch assigned Jira issues and stage new ones for approval. No tasks created."""
    config = await get_jira_config(db)
    if not config or not config.get("enabled"):
        return {"skipped": True, "reason": "Jira not configured or disabled"}
    client = JiraClient(base_url=config["base_url"], email=config["email"],
                        api_token=config["api_token"])
    issues = await client.search_issues(jql)

    staged, skipped = [], []
    for issue in issues:
        key = issue.get("key", "")
        # Honor the BX-only allowlist on the way in, too.
        if not is_allowed_jira_key(key):
            skipped.append({"jira_key": key, "reason": "not an allowed project"})
            continue
        if await task_exists_for_jira_key(db, key):
            skipped.append({"jira_key": key, "reason": "already imported"})
            continue
        if await pending_import_exists(db, key):
            skipped.append({"jira_key": key, "reason": "already pending"})
            continue
        await insert_pending_import(
            db, id=str(uuid.uuid4()), jira_key=key,
            summary=_field(issue, "summary", default="") or "",
            issue_type=(_field(issue, "issuetype", "name", default="") or ""),
            priority=(_field(issue, "priority", "name", default="") or ""),
            jira_status=(_field(issue, "status", "name", default="") or ""),
            raw_json=json.dumps(issue),
        )
        staged.append(key)
    return {"staged": staged, "skipped": skipped,
            "staged_count": len(staged), "fetched": len(issues)}


async def approve_import(
    db: aiosqlite.Connection, import_id: str, *, project_id: str,
    assigned_to: str = "", write_obsidian: bool = True,
) -> dict:
    """Approve one staged issue: create the linked Slate task in ``project_id``."""
    pending = await get_pending_import(db, import_id)
    if not pending:
        return {"error": "pending import not found"}
    if pending["status"] != "pending":
        return {"error": f"already {pending['status']}"}

    key = pending["jira_key"]
    if await task_exists_for_jira_key(db, key):
        await set_pending_import_decided(db, import_id=import_id, status="superseded")
        return {"error": "a task already exists for this Jira key", "jira_key": key}

    tid = str(uuid.uuid4())
    task_type = _TYPE_MAP.get((pending.get("issue_type") or "").lower(), "feature")
    priority = _PRIORITY_MAP.get((pending.get("priority") or "").lower(), "medium")
    await insert_task(
        db, id=tid, project_id=project_id,
        title=pending.get("summary") or key, type=task_type, priority=priority,
        created_by="jira-import", assigned_to=assigned_to, jira_issue_key=key,
    )
    await set_pending_import_decided(
        db, import_id=import_id, status="imported", project_id=project_id, task_id=tid,
    )

    result = {"task_id": tid, "jira_key": key, "project_id": project_id}
    if write_obsidian:
        try:
            from slate.obsidian.vault import write_issue_doc
            ctx = await get_task_context(db, tid)
            path = write_issue_doc(key, ctx, title=pending.get("summary"))
            if path:
                result["obsidian"] = str(path)
        except Exception as e:  # noqa: BLE001 — Obsidian is best-effort, never blocks import
            result["obsidian_error"] = str(e)[:200]
    return result


async def reject_import(db: aiosqlite.Connection, import_id: str) -> dict:
    pending = await get_pending_import(db, import_id)
    if not pending:
        return {"error": "pending import not found"}
    await set_pending_import_decided(db, import_id=import_id, status="rejected")
    return {"rejected": True, "jira_key": pending["jira_key"]}
