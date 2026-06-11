"""Auto-refresh the Obsidian doc for a task as work happens.

Closes the memory loop: whenever a worklog, decision, heartbeat, or state change
lands, the issue's markdown doc is regenerated so the vault always mirrors Slate's
current facts (the freeform notes an agent wrote are preserved — see vault.py).

Everything here is **best-effort**: no vault configured, or any filesystem error,
returns None and never raises, so it can be called from the hot path of a CLI
command or API route without risk of breaking the underlying operation.
"""
from __future__ import annotations
from typing import Optional
import aiosqlite
from slate.db.queries import get_task_context
from slate.obsidian.vault import write_issue_doc, read_freeform


async def refresh_doc_for_task(
    db: aiosqlite.Connection, task_id: str, *, subfolder: str = "slate",
) -> Optional[str]:
    """Regenerate the Obsidian doc for ``task_id``'s linked Jira issue.

    Returns the path written (str) or None if there's no vault, no task, or no
    Jira key. Swallows all errors — the caller's primary operation must not fail
    because the vault is unreachable.
    """
    try:
        ctx = await get_task_context(db, task_id)
        task = ctx.get("task")
        if not task or not task.get("jira_issue_key"):
            return None
        path = write_issue_doc(
            task["jira_issue_key"], ctx, title=task.get("title"), subfolder=subfolder,
        )
        return str(path) if path else None
    except Exception:  # noqa: BLE001 — best-effort; never break the caller
        return None


async def freeform_for_task(
    db: aiosqlite.Connection, task_id: str, *, subfolder: str = "slate",
) -> Optional[str]:
    """The human/agent-authored notes from the task's Obsidian doc, if any."""
    try:
        task = (await get_task_context(db, task_id)).get("task")
        if not task or not task.get("jira_issue_key"):
            return None
        return read_freeform(task["jira_issue_key"], subfolder)
    except Exception:  # noqa: BLE001
        return None
