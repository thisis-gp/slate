from __future__ import annotations
import time
import aiosqlite
from typing import Any, Optional


def _looks_like_uuid(s: str) -> bool:
    # UUIDs have 4 hyphens and hex segments
    parts = s.split("-")
    return len(parts) == 5 and all(len(p) in (8, 4, 4, 4, 12) for p in parts)


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
         jira_issue_key.upper() if jira_issue_key else None, now, now),
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
                       body: str, author_type: str = "agent") -> dict:
    now = time.time()
    task = await get_task(db, task_id)
    full_id = task["id"] if task else task_id
    async with db.execute(
        "INSERT INTO comments (task_id, author, author_type, body, ts) VALUES (?, ?, ?, ?, ?) RETURNING *",
        (full_id, author, author_type, body, now),
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
    return {"task": task, "runs": runs, "transitions": transitions, "comments": comments}


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


import uuid as _uuid


async def upsert_jira_config(
    db: aiosqlite.Connection, *,
    base_url: str, email: str, api_token: str,
    sync_time: str = "09:00", state_map: str = "", enabled: bool = True,
) -> None:
    await db.execute(
        "INSERT INTO jira_config (id, base_url, email, api_token, sync_time, state_map, enabled) "
        "VALUES (1, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET base_url=excluded.base_url, email=excluded.email, "
        "api_token=excluded.api_token, sync_time=excluded.sync_time, "
        "state_map=excluded.state_map, enabled=excluded.enabled",
        (base_url, email, api_token, sync_time, state_map or None, 1 if enabled else 0),
    )
    await db.commit()


async def get_jira_config(db: aiosqlite.Connection) -> Optional[dict]:
    async with db.execute("SELECT * FROM jira_config WHERE id = 1") as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_task_jira_key(db: aiosqlite.Connection, *, task_id: str, jira_key: str) -> None:
    task = await get_task(db, task_id)
    full_id = task["id"] if task else task_id
    now = time.time()
    await db.execute(
        "UPDATE tasks SET jira_issue_key = ?, updated_at = ? WHERE id = ?",
        (jira_key.upper(), now, full_id),
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
    now = time.time()
    await db.execute(
        "INSERT INTO jira_sync_log (id, task_id, jira_key, run_id, action, status, detail, synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(_uuid.uuid4()), task_id, jira_key, run_id or None, action, status, detail or None, now),
    )
    await db.commit()


async def get_unsynced_runs(db: aiosqlite.Connection, task_id: str, jira_key: str) -> list[dict]:
    async with db.execute(
        """SELECT ar.* FROM agent_runs ar
           WHERE ar.task_id = ?
           AND NOT EXISTS (
               SELECT 1 FROM jira_sync_log jsl
               WHERE jsl.run_id = ar.id AND jsl.action = 'worklog' AND jsl.status = 'ok'
           )
           ORDER BY ar.started_at ASC""",
        (task_id,),
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
