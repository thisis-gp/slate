from __future__ import annotations
import os
import time
import uuid as _uuid
import aiosqlite
from typing import Any, Optional
from slate.jira.mapping import (
    allowed_jira_prefixes, normalize_jira_key, is_allowed_jira_key,
)


def _looks_like_uuid(s: str) -> bool:
    # UUIDs have 4 hyphens and hex segments
    parts = s.split("-")
    return len(parts) == 5 and all(len(p) in (8, 4, 4, 4, 12) for p in parts)


def _validate_jira_key(jira_key: str) -> str:
    """Normalize + validate a Jira key against the allowed prefixes.

    Returns the normalized key, or raises ValueError if it is not allowed.
    """
    norm = normalize_jira_key(jira_key)
    if not is_allowed_jira_key(norm):
        raise ValueError(
            f"Invalid Jira key {norm!r} — expected {allowed_jira_prefixes() or 'PREFIX'}-<number>, e.g. BX-3023"
        )
    return norm


async def insert_project(db: aiosqlite.Connection, *, id: str, name: str,
                          description: str = "", status: str = "active",
                          key: str = "") -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO projects (id, name, description, status, key, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (id, name, description, status, key.upper() or None, now, now),
    )
    await db.commit()


async def get_project(db: aiosqlite.Connection, project_id: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM projects WHERE id = ? OR key = ?", (project_id, project_id.upper())
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_projects(db: aiosqlite.Connection, status: str = "active") -> list[dict]:
    async with db.execute(
        "SELECT * FROM projects WHERE status = ? ORDER BY created_at DESC", (status,)
    ) as cur:
        return [dict(r) async for r in cur]


async def insert_task(db: aiosqlite.Connection, *, id: str, project_id: str,
                       title: str, description: str = "", type: str = "feature",
                       priority: str = "medium", created_by: str = "human",
                       reporter: str = "", assigned_to: str = "",
                       parent_task_id: str = "", sprint_id: str = "",
                       story_points: int = 0, labels: str = "",
                       links: str = "", jira_issue_key: str = "") -> None:
    now = time.time()
    # Validate any provided Jira key against the allowed prefixes
    norm_jira_key = _validate_jira_key(jira_issue_key) if jira_issue_key else None
    # Resolve project to full ID if a key was passed (e.g. "BX")
    proj = await get_project(db, project_id)
    full_project_id = proj["id"] if proj else project_id
    # Auto-increment number per project
    async with db.execute(
        "SELECT COALESCE(MAX(number), 0) + 1 FROM tasks WHERE project_id = ?", (full_project_id,)
    ) as cur:
        row = await cur.fetchone()
        number = row[0] if row else 1
    await db.execute(
        "INSERT INTO tasks (id, project_id, parent_task_id, sprint_id, number, title, "
        "description, type, state, priority, created_by, reporter, assigned_to, "
        "story_points, labels, links, jira_issue_key, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (id, full_project_id, parent_task_id or None, sprint_id or None, number,
         title, description, type, priority, created_by, reporter or None,
         assigned_to or None, story_points or None, labels or None, links or None,
         norm_jira_key, now, now),
    )
    await db.execute(
        "INSERT INTO state_transitions (task_id, from_state, to_state, changed_by, ts) "
        "VALUES (?, NULL, 'todo', ?, ?)",
        (id, created_by, now),
    )
    await db.commit()


async def get_task(db: aiosqlite.Connection, task_id: str) -> Optional[dict]:
    # Ticket ID format: KEY-NUMBER (e.g. BX-42)
    if "-" in task_id and not _looks_like_uuid(task_id):
        parts = task_id.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            key, number = parts[0].upper(), int(parts[1])
            async with db.execute(
                "SELECT t.* FROM tasks t JOIN projects p ON t.project_id = p.id "
                "WHERE p.key = ? AND t.number = ?", (key, number)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
    # UUID or prefix
    async with db.execute(
        "SELECT * FROM tasks WHERE id = ? OR id LIKE ?", (task_id, f"{task_id}%")
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_tasks(db: aiosqlite.Connection, project_id: str = "",
                      state: str = "", assigned_to: str = "") -> list[dict]:
    conditions, params = [], []
    if project_id:
        conditions.append("(project_id = ? OR project_id LIKE ?)")
        params.extend([project_id, f"{project_id}%"])
    if state:
        conditions.append("state = ?")
        params.append(state)
    if assigned_to:
        conditions.append("assigned_to = ?")
        params.append(assigned_to)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    async with db.execute(
        f"SELECT * FROM tasks {where} ORDER BY created_at DESC", params
    ) as cur:
        return [dict(r) async for r in cur]


async def update_task_state(db: aiosqlite.Connection, *, task_id: str,
                             to_state: str, changed_by: str,
                             reason: str = "", new_assignee: str = "") -> None:
    now = time.time()
    # Resolve ticket ID format (BX-42) or UUID prefix
    task = await get_task(db, task_id)
    if task:
        full_id = task["id"]
        from_state = task["state"]
    else:
        full_id = task_id
        from_state = None
    update_parts = ["state = ?", "updated_at = ?"]
    update_params: list[Any] = [to_state, now]
    if new_assignee:
        update_parts.append("assigned_to = ?")
        update_params.append(new_assignee)
    update_params.append(full_id)
    await db.execute(
        f"UPDATE tasks SET {', '.join(update_parts)} WHERE id = ?", update_params
    )
    await db.execute(
        "INSERT INTO state_transitions (task_id, from_state, to_state, changed_by, reason, new_assignee, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (full_id, from_state, to_state, changed_by, reason or None, new_assignee or None, now),
    )
    await db.commit()


async def add_comment(db: aiosqlite.Connection, *, task_id: str, author: str,
                       body: str, author_type: str = "agent",
                       kind: str = "note") -> dict:
    now = time.time()
    task = await get_task(db, task_id)
    full_id = task["id"] if task else task_id
    async with db.execute(
        "INSERT INTO comments (task_id, author, author_type, kind, body, ts) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
        (full_id, author, author_type, kind, body, now),
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else {}


async def list_comments(db: aiosqlite.Connection, task_id: str) -> list[dict]:
    task = await get_task(db, task_id)
    full_id = task["id"] if task else task_id
    async with db.execute(
        "SELECT * FROM comments WHERE task_id = ? ORDER BY ts ASC", (full_id,)
    ) as cur:
        return [dict(r) async for r in cur]


async def insert_session(db: aiosqlite.Connection, *, id: str, agent_name: str,
                          tool: str = "", project_id: str = "",
                          date: str) -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO sessions (id, agent_name, tool, project_id, date, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (id, agent_name, tool or None, project_id or None, date, now),
    )
    await db.commit()


async def end_session(db: aiosqlite.Connection, *, session_id: str,
                       summary: str = "", total_cost_usd: float = 0.0) -> None:
    now = time.time()
    await db.execute(
        "UPDATE sessions SET ended_at = ?, summary = ?, total_cost_usd = ? WHERE id = ?",
        (now, summary or None, total_cost_usd, session_id),
    )
    await db.commit()


async def insert_agent_run(db: aiosqlite.Connection, *, id: str, task_id: str,
                            agent_name: str, tool: str, summary: str,
                            session_id: str = "", outcome: str = "",
                            status: str = "completed", cost_usd: float = 0.0,
                            commit_sha: str = "", commit_message: str = "") -> None:
    now = time.time()
    # Resolve short ID prefix or ticket ID to full UUID
    task = await get_task(db, task_id)
    full_task_id = task["id"] if task else task_id
    await db.execute(
        "INSERT INTO agent_runs (id, task_id, session_id, agent_name, tool, summary, "
        "outcome, status, commit_sha, commit_message, started_at, completed_at, cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (id, full_task_id, session_id or None, agent_name, tool, summary,
         outcome or None, status, commit_sha or None, commit_message or None,
         now, now, cost_usd),
    )
    await db.commit()


async def get_task_context(db: aiosqlite.Connection, task_id: str) -> dict[str, Any]:
    task = await get_task(db, task_id)
    full_id = task["id"] if task else task_id
    async with db.execute(
        "SELECT * FROM agent_runs WHERE task_id = ? ORDER BY started_at ASC", (full_id,)
    ) as cur:
        runs = [dict(r) async for r in cur]
    async with db.execute(
        "SELECT * FROM state_transitions WHERE task_id = ? ORDER BY ts ASC", (full_id,)
    ) as cur:
        transitions = [dict(r) async for r in cur]
    async with db.execute(
        "SELECT * FROM comments WHERE task_id = ? ORDER BY ts ASC", (full_id,)
    ) as cur:
        comments = [dict(r) async for r in cur]
    async with db.execute(
        "SELECT * FROM worklogs WHERE task_id = ? ORDER BY started_at ASC", (full_id,)
    ) as cur:
        worklogs = [dict(r) async for r in cur]
    # Convenience splits for an agent reading the brief before starting work.
    decisions = [c for c in comments if c.get("kind") == "decision"]
    heartbeats = [c for c in comments if c.get("kind") == "heartbeat"]
    notes = [c for c in comments if c.get("kind") not in ("decision", "heartbeat")]
    return {
        "task": task, "runs": runs, "transitions": transitions,
        "comments": comments, "worklogs": worklogs,
        "decisions": decisions, "heartbeats": heartbeats, "notes": notes,
        "latest_heartbeat": heartbeats[-1] if heartbeats else None,
    }


async def get_daily_sync(db: aiosqlite.Connection, date: str) -> dict[str, Any]:
    async with db.execute(
        "SELECT * FROM sessions WHERE date = ? ORDER BY started_at ASC", (date,)
    ) as cur:
        sessions = [dict(r) async for r in cur]
    async with db.execute(
        "SELECT ar.*, t.title as task_title FROM agent_runs ar "
        "JOIN tasks t ON ar.task_id = t.id "
        "WHERE date(ar.started_at, 'unixepoch') = ? ORDER BY ar.started_at ASC",
        (date,),
    ) as cur:
        runs = [dict(r) async for r in cur]
    async with db.execute(
        "SELECT st.*, t.title as task_title FROM state_transitions st "
        "JOIN tasks t ON st.task_id = t.id "
        "WHERE date(st.ts, 'unixepoch') = ? ORDER BY st.ts ASC",
        (date,),
    ) as cur:
        transitions = [dict(r) async for r in cur]
    async with db.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_runs "
        "WHERE date(started_at, 'unixepoch') = ?",
        (date,),
    ) as cur:
        row = await cur.fetchone()
        total_cost = row[0] if row else 0.0
    return {
        "date": date,
        "sessions": sessions,
        "runs": runs,
        "transitions": transitions,
        "total_cost_usd": total_cost,
    }


async def insert_sprint(db, *, id: str, project_id: str, name: str,
                         goal: str = "", start_date: str = "", end_date: str = "") -> None:
    now = time.time()
    proj = await get_project(db, project_id)
    full_project_id = proj["id"] if proj else project_id
    await db.execute(
        "INSERT INTO sprints (id, project_id, name, goal, start_date, end_date, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (id, full_project_id, name, goal or None, start_date or None, end_date or None, now),
    )
    await db.commit()


async def get_sprint(db, sprint_id: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM sprints WHERE id = ? OR id LIKE ?", (sprint_id, f"{sprint_id}%")
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_sprints(db, project_id: str = "", status: str = "") -> list[dict]:
    conditions, params = [], []
    if project_id:
        proj = await get_project(db, project_id)
        full_project_id = proj["id"] if proj else project_id
        conditions.append("project_id = ?")
        params.append(full_project_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    async with db.execute(
        f"SELECT * FROM sprints {where} ORDER BY created_at DESC", params
    ) as cur:
        return [dict(r) async for r in cur]


async def update_sprint_status(db, sprint_id: str, status: str) -> None:
    sprint = await get_sprint(db, sprint_id)
    full_id = sprint["id"] if sprint else sprint_id
    await db.execute("UPDATE sprints SET status = ? WHERE id = ?", (status, full_id))
    await db.commit()


async def assign_task_to_sprint(db, task_id: str, sprint_id: str) -> None:
    task = await get_task(db, task_id)
    full_task_id = task["id"] if task else task_id
    sprint = await get_sprint(db, sprint_id)
    full_sprint_id = sprint["id"] if sprint else sprint_id
    now = time.time()
    await db.execute(
        "UPDATE tasks SET sprint_id = ?, updated_at = ? WHERE id = ?",
        (full_sprint_id, now, full_task_id)
    )
    await db.commit()


async def get_sprint_tasks(db, sprint_id: str) -> list[dict]:
    sprint = await get_sprint(db, sprint_id)
    full_id = sprint["id"] if sprint else sprint_id
    async with db.execute(
        "SELECT * FROM tasks WHERE sprint_id = ? ORDER BY created_at ASC", (full_id,)
    ) as cur:
        return [dict(r) async for r in cur]


async def upsert_jira_config(
    db: aiosqlite.Connection, *,
    base_url: str, email: str, api_token: str,
    sync_time: str = "09:00", worklog_sync_time: str = "11:00",
    state_map: str = "", enabled: bool = True,
) -> None:
    await db.execute(
        "INSERT INTO jira_config (id, base_url, email, api_token, sync_time, worklog_sync_time, state_map, enabled) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET base_url=excluded.base_url, email=excluded.email, "
        "api_token=excluded.api_token, sync_time=excluded.sync_time, "
        "worklog_sync_time=excluded.worklog_sync_time, "
        "state_map=excluded.state_map, enabled=excluded.enabled",
        (base_url, email, api_token, sync_time, worklog_sync_time, state_map or None, 1 if enabled else 0),
    )
    await db.commit()


async def get_jira_config(db: aiosqlite.Connection) -> Optional[dict]:
    """Resolve Jira config from the DB, falling back to JIRA_* env vars.

    Env lets you configure Jira without storing the token in the DB. Env credentials
    win where present so token rotation in .env takes effect after a restart.
    Returns None if there are no usable credentials (base_url + email + api_token).
    """
    async with db.execute("SELECT * FROM jira_config WHERE id = 1") as cur:
        row = await cur.fetchone()
    cfg = dict(row) if row else {}
    env_base_url = os.getenv("JIRA_BASE_URL", "").strip()
    env_email = os.getenv("JIRA_EMAIL", "").strip()
    env_api_token = os.getenv("JIRA_API_TOKEN", "").strip()
    cfg["base_url"] = (env_base_url or cfg.get("base_url") or "").strip().rstrip("/")
    cfg["email"] = (env_email or cfg.get("email") or "").strip()
    cfg["api_token"] = (env_api_token or cfg.get("api_token") or "").strip()
    cfg["sync_time"] = cfg.get("sync_time") or os.getenv("JIRA_SYNC_TIME", "09:00")
    cfg.setdefault("worklog_sync_time", os.getenv("JIRA_WORKLOG_SYNC_TIME", cfg["sync_time"]))
    if not cfg.get("state_map"):
        cfg["state_map"] = os.getenv("JIRA_STATE_MAP", "") or None
    has_creds = bool(cfg["base_url"] and cfg["email"] and cfg["api_token"])
    if not has_creds:
        return None
    # DB 'enabled' wins if a row existed; env-derived config is enabled by default.
    cfg["enabled"] = bool(cfg.get("enabled")) if row is not None else True
    return cfg


async def update_task_jira_key(db: aiosqlite.Connection, *, task_id: str, jira_key: str) -> None:
    norm_key = _validate_jira_key(jira_key)
    task = await get_task(db, task_id)
    full_id = task["id"] if task else task_id
    now = time.time()
    await db.execute(
        "UPDATE tasks SET jira_issue_key = ?, updated_at = ? WHERE id = ?",
        (norm_key, now, full_id),
    )
    await db.commit()


async def list_tasks_with_jira(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        "SELECT * FROM tasks WHERE jira_issue_key IS NOT NULL ORDER BY created_at ASC"
    ) as cur:
        return [dict(r) async for r in cur]


async def insert_jira_sync_log(
    db: aiosqlite.Connection, *,
    task_id: str, jira_key: str, action: str, status: str,
    detail: str = "", run_id: str = "",
) -> None:
    task = await get_task(db, task_id)
    full_task_id = task["id"] if task else task_id
    now = time.time()
    await db.execute(
        "INSERT INTO jira_sync_log (id, task_id, jira_key, run_id, action, status, detail, synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(_uuid.uuid4()), full_task_id, jira_key, run_id or None, action, status, detail or None, now),
    )
    await db.commit()


async def get_unsynced_runs(db: aiosqlite.Connection, task_id: str, jira_key: str) -> list[dict]:
    task = await get_task(db, task_id)
    full_task_id = task["id"] if task else task_id
    async with db.execute(
        """SELECT ar.* FROM agent_runs ar
           WHERE ar.task_id = ?
           AND NOT EXISTS (
               SELECT 1 FROM jira_sync_log jsl
               WHERE jsl.run_id = ar.id AND jsl.jira_key = ? AND jsl.action = 'worklog' AND jsl.status = 'ok'
           )
           ORDER BY ar.started_at ASC""",
        (full_task_id, jira_key),
    ) as cur:
        return [dict(r) async for r in cur]


async def list_jira_sync_log(db: aiosqlite.Connection, task_id: str = "", limit: int = 50) -> list[dict]:
    if task_id:
        task = await get_task(db, task_id)
        full_id = task["id"] if task else task_id
        async with db.execute(
            "SELECT * FROM jira_sync_log WHERE task_id = ? ORDER BY synced_at DESC LIMIT ?",
            (full_id, limit),
        ) as cur:
            return [dict(r) async for r in cur]
    async with db.execute(
        "SELECT * FROM jira_sync_log ORDER BY synced_at DESC LIMIT ?", (limit,)
    ) as cur:
        return [dict(r) async for r in cur]


# ── Worklog queries ───────────────────────────────────────────────────────────

async def insert_worklog(
    db: aiosqlite.Connection, *,
    id: str, task_id: str, agent_run_id: str = "",
    agent_name: str, tool: str, summary: str,
    time_spent_seconds: int = 0,
) -> None:
    task = await get_task(db, task_id)
    full_task_id = task["id"] if task else task_id
    now = time.time()
    await db.execute(
        "INSERT INTO worklogs (id, task_id, agent_run_id, agent_name, tool, summary, "
        "time_spent_seconds, started_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (id, full_task_id, agent_run_id or None, agent_name, tool, summary,
         max(60, time_spent_seconds), now, now),
    )
    await db.commit()


async def list_worklogs(db: aiosqlite.Connection, task_id: str = "",
                         synced_only: bool = False, unsynced_only: bool = False) -> list[dict]:
    conditions, params = [], []
    if task_id:
        task = await get_task(db, task_id)
        full_id = task["id"] if task else task_id
        conditions.append("task_id = ?")
        params.append(full_id)
    if synced_only:
        conditions.append("synced_to_jira = 1")
    if unsynced_only:
        conditions.append("synced_to_jira = 0")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    async with db.execute(
        f"SELECT * FROM worklogs {where} ORDER BY started_at ASC", params
    ) as cur:
        return [dict(r) async for r in cur]


async def get_unsynced_worklogs(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        """SELECT w.*, t.jira_issue_key FROM worklogs w
           JOIN tasks t ON w.task_id = t.id
           WHERE w.synced_to_jira = 0 AND t.jira_issue_key IS NOT NULL
           ORDER BY w.started_at ASC"""
    ) as cur:
        return [dict(r) async for r in cur]


async def get_unsynced_worklogs_by_ids(
    db: aiosqlite.Connection, worklog_ids: list[str],
) -> list[dict]:
    if not worklog_ids:
        return []
    placeholders = ",".join("?" for _ in worklog_ids)
    async with db.execute(
        f"""SELECT w.*, t.jira_issue_key FROM worklogs w
            JOIN tasks t ON w.task_id = t.id
            WHERE w.synced_to_jira = 0
            AND t.jira_issue_key IS NOT NULL
            AND w.id IN ({placeholders})
            ORDER BY w.started_at ASC""",
        worklog_ids,
    ) as cur:
        return [dict(r) async for r in cur]


async def count_unlinked_worklogs(db: aiosqlite.Connection) -> int:
    """Count unsynced worklogs whose task has no Jira key (pending a Jira key)."""
    async with db.execute(
        """SELECT COUNT(*) FROM worklogs w
           JOIN tasks t ON w.task_id = t.id
           WHERE w.synced_to_jira = 0
           AND (t.jira_issue_key IS NULL OR t.jira_issue_key = '')"""
    ) as cur:
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def mark_worklog_synced(db: aiosqlite.Connection, worklog_id: str,
                               jira_worklog_id: str = "") -> None:
    now = time.time()
    await db.execute(
        "UPDATE worklogs SET synced_to_jira = 1, jira_worklog_id = ?, synced_at = ? WHERE id = ?",
        (jira_worklog_id or None, now, worklog_id),
    )
    await db.commit()


async def claim_worklogs_for_push(
    db: aiosqlite.Connection, worklog_ids: list[str], token: str,
) -> list[dict]:
    """Atomically claim unsynced worklogs for a Jira push, returning the claimed rows.

    Flips ``synced_to_jira`` 0→1 and stamps ``jira_worklog_id`` with a transient
    ``token`` in a single conditional UPDATE. SQLite serializes writers, so a
    concurrent approval (same process or another) that targets the same rows finds
    them already synced and claims **zero** — this is what prevents a duplicate
    Jira worklog. The claim is finalized with the real Jira id on success, or
    released back to unsynced on failure / crash recovery.
    """
    if not worklog_ids:
        return []
    placeholders = ",".join("?" for _ in worklog_ids)
    now = time.time()
    await db.execute(
        f"UPDATE worklogs SET synced_to_jira = 1, jira_worklog_id = ?, synced_at = ? "
        f"WHERE synced_to_jira = 0 AND id IN ({placeholders})",
        (token, now, *worklog_ids),
    )
    await db.commit()
    async with db.execute(
        f"""SELECT w.*, t.jira_issue_key FROM worklogs w
            JOIN tasks t ON w.task_id = t.id
            WHERE w.jira_worklog_id = ? AND w.id IN ({placeholders})
            ORDER BY w.started_at ASC""",
        (token, *worklog_ids),
    ) as cur:
        return [dict(r) async for r in cur]


async def finalize_worklog_claims(
    db: aiosqlite.Connection, worklog_ids: list[str], jira_worklog_id: str,
) -> None:
    """Stamp the real Jira worklog id onto rows claimed for a successful push."""
    if not worklog_ids:
        return
    placeholders = ",".join("?" for _ in worklog_ids)
    await db.execute(
        f"UPDATE worklogs SET jira_worklog_id = ? WHERE id IN ({placeholders})",
        (jira_worklog_id or None, *worklog_ids),
    )
    await db.commit()


async def release_worklog_claims(db: aiosqlite.Connection, token: str) -> int:
    """Release worklogs still held by ``token`` back to unsynced (failure/recovery).

    Returns the number released. Only touches rows still carrying the transient
    token, so finalized (successfully pushed) rows are never reverted.
    """
    cur = await db.execute(
        "UPDATE worklogs SET synced_to_jira = 0, jira_worklog_id = NULL, synced_at = NULL "
        "WHERE jira_worklog_id = ? AND synced_to_jira = 1",
        (token,),
    )
    await db.commit()
    return cur.rowcount if cur.rowcount is not None else 0


async def release_stale_worklog_claims(
    db: aiosqlite.Connection, older_than_seconds: int = 600,
) -> int:
    """Recover orphaned claims: rows left in the transient ``claiming:`` state by a
    process that crashed between claiming and pushing. Anything older than the
    cutoff (default 10 min — far longer than any real push) is returned to unsynced
    so the next batch picks it up. Returns the number recovered.
    """
    cutoff = time.time() - older_than_seconds
    cur = await db.execute(
        "UPDATE worklogs SET synced_to_jira = 0, jira_worklog_id = NULL, synced_at = NULL "
        "WHERE synced_to_jira = 1 AND jira_worklog_id LIKE 'claiming:%' "
        "AND (synced_at IS NULL OR synced_at < ?)",
        (cutoff,),
    )
    await db.commit()
    return cur.rowcount if cur.rowcount is not None else 0


async def get_task_worklogs_for_jira_sync(db: aiosqlite.Connection, task_id: str) -> list[dict]:
    """Get all unsynced worklogs for a task, aggregated for Jira bulk sync."""
    task = await get_task(db, task_id)
    full_id = task["id"] if task else task_id
    async with db.execute(
        """SELECT * FROM worklogs
           WHERE task_id = ? AND synced_to_jira = 0
           ORDER BY started_at ASC""",
        (full_id,),
    ) as cur:
        return [dict(r) async for r in cur]


# ── Jira pending sync queries ─────────────────────────────────────────────────

async def insert_pending_sync(
    db: aiosqlite.Connection, *,
    id: str, batch_json: str, summary_provider: str = "",
) -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO jira_pending_sync (id, created_at, status, batch_json, summary_provider) "
        "VALUES (?, ?, 'pending', ?, ?)",
        (id, now, batch_json, summary_provider or None),
    )
    await db.commit()


async def get_latest_pending(db: aiosqlite.Connection) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM jira_pending_sync WHERE status = 'pending' "
        "ORDER BY created_at DESC LIMIT 1"
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_pending(db: aiosqlite.Connection, pending_id: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM jira_pending_sync WHERE id = ?", (pending_id,)
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_pending_status(
    db: aiosqlite.Connection, pending_id: str, status: str, result_json: str = "",
) -> None:
    now = time.time()
    await db.execute(
        "UPDATE jira_pending_sync SET status = ?, decided_at = ?, result_json = ? WHERE id = ?",
        (status, now, result_json or None, pending_id),
    )
    await db.commit()


# ── Notification queries ──────────────────────────────────────────────────────

async def insert_notification(
    db: aiosqlite.Connection, *,
    id: str, type: str, task_id: str = "",
    title: str, body: str,
    channel: str = "console", destination: str = "",
) -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO notifications (id, type, task_id, title, body, channel, destination, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (id, type, task_id or None, title, body, channel, destination or None, now),
    )
    await db.commit()


async def list_pending_notifications(db: aiosqlite.Connection, limit: int = 100) -> list[dict]:
    async with db.execute(
        "SELECT * FROM notifications WHERE sent = 0 ORDER BY created_at ASC LIMIT ?", (limit,)
    ) as cur:
        return [dict(r) async for r in cur]


async def mark_notification_sent(db: aiosqlite.Connection, notification_id: str) -> None:
    now = time.time()
    await db.execute(
        "UPDATE notifications SET sent = 1, sent_at = ? WHERE id = ?",
        (now, notification_id),
    )
    await db.commit()


async def insert_notification_rule(
    db: aiosqlite.Connection, *,
    name: str, event_type: str, condition: str = "",
    channel: str = "webhook", destination: str = "",
    enabled: bool = True,
) -> None:
    await db.execute(
        "INSERT INTO notification_rules (name, event_type, condition, channel, destination, enabled) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, event_type, condition or None, channel, destination, 1 if enabled else 0),
    )
    await db.commit()


async def list_notification_rules(db: aiosqlite.Connection, enabled_only: bool = True) -> list[dict]:
    if enabled_only:
        async with db.execute(
            "SELECT * FROM notification_rules WHERE enabled = 1 ORDER BY id ASC"
        ) as cur:
            return [dict(r) async for r in cur]
    async with db.execute(
        "SELECT * FROM notification_rules ORDER BY id ASC"
    ) as cur:
        return [dict(r) async for r in cur]


# ── Scheduler state (daily missed-run recovery) ───────────────────────────────

async def get_scheduler_last_run(db: aiosqlite.Connection, name: str) -> Optional[str]:
    """Return the local date (YYYY-MM-DD) a named scheduler last fired, or None."""
    async with db.execute(
        "SELECT last_run_on FROM scheduler_state WHERE name = ?", (name,)
    ) as cur:
        row = await cur.fetchone()
    return row["last_run_on"] if row else None


async def set_scheduler_last_run(db: aiosqlite.Connection, name: str, day: str) -> None:
    await db.execute(
        "INSERT INTO scheduler_state (name, last_run_on, updated_at) "
        "VALUES (?, ?, unixepoch('now', 'subsec')) "
        "ON CONFLICT(name) DO UPDATE SET "
        "last_run_on = excluded.last_run_on, updated_at = excluded.updated_at",
        (name, day),
    )
    await db.commit()


# ── Jira -> Slate import staging (always human-approved) ──────────────────────

async def task_exists_for_jira_key(db: aiosqlite.Connection, jira_key: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM tasks WHERE jira_issue_key = ? LIMIT 1", (jira_key,)
    ) as cur:
        return await cur.fetchone() is not None


async def pending_import_exists(db: aiosqlite.Connection, jira_key: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM jira_pending_import WHERE jira_key = ? AND status = 'pending' LIMIT 1",
        (jira_key,),
    ) as cur:
        return await cur.fetchone() is not None


async def insert_pending_import(db: aiosqlite.Connection, *, id: str, jira_key: str,
                                 summary: str = "", issue_type: str = "",
                                 priority: str = "", jira_status: str = "",
                                 raw_json: str = "") -> None:
    await db.execute(
        "INSERT INTO jira_pending_import (id, jira_key, summary, issue_type, priority, "
        "jira_status, raw_json, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (id, jira_key, summary or None, issue_type or None, priority or None,
         jira_status or None, raw_json or None),
    )
    await db.commit()


async def list_pending_imports(db: aiosqlite.Connection, status: str = "pending") -> list[dict]:
    async with db.execute(
        "SELECT * FROM jira_pending_import WHERE status = ? ORDER BY created_at ASC",
        (status,),
    ) as cur:
        return [dict(r) async for r in cur]


async def get_pending_import(db: aiosqlite.Connection, import_id: str) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM jira_pending_import WHERE id = ?", (import_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def set_pending_import_decided(db: aiosqlite.Connection, *, import_id: str,
                                      status: str, project_id: str = "",
                                      task_id: str = "") -> None:
    await db.execute(
        "UPDATE jira_pending_import SET status = ?, project_id = ?, task_id = ?, "
        "decided_at = unixepoch('now', 'subsec') WHERE id = ?",
        (status, project_id or None, task_id or None, import_id),
    )
    await db.commit()
