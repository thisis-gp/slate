from __future__ import annotations
import time
import aiosqlite
from typing import Any, Optional


async def insert_project(db: aiosqlite.Connection, *, id: str, name: str,
                          description: str = "", status: str = "active") -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO projects (id, name, description, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (id, name, description, status, now, now),
    )
    await db.commit()


async def get_project(db: aiosqlite.Connection, project_id: str) -> Optional[dict]:
    async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cur:
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
                       assigned_to: str = "", parent_task_id: str = "",
                       sprint_id: str = "") -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO tasks (id, project_id, parent_task_id, sprint_id, title, "
        "description, type, state, priority, created_by, assigned_to, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?)",
        (id, project_id, parent_task_id or None, sprint_id or None,
         title, description, type, priority, created_by, assigned_to or None, now, now),
    )
    await db.execute(
        "INSERT INTO state_transitions (task_id, from_state, to_state, changed_by, ts) "
        "VALUES (?, NULL, 'todo', ?, ?)",
        (id, created_by, now),
    )
    await db.commit()


async def get_task(db: aiosqlite.Connection, task_id: str) -> Optional[dict]:
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
                             reason: str = "") -> None:
    now = time.time()
    async with db.execute(
        "SELECT id, state FROM tasks WHERE id = ? OR id LIKE ?", (task_id, f"{task_id}%")
    ) as cur:
        row = await cur.fetchone()
        full_id = row[0] if row else task_id
        from_state = row[1] if row else None
    await db.execute(
        "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
        (to_state, now, full_id),
    )
    await db.execute(
        "INSERT INTO state_transitions (task_id, from_state, to_state, changed_by, reason, ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (full_id, from_state, to_state, changed_by, reason or None, now),
    )
    await db.commit()


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
                            status: str = "completed",
                            cost_usd: float = 0.0) -> None:
    now = time.time()
    # Resolve short ID prefix to full UUID
    task = await get_task(db, task_id)
    full_task_id = task["id"] if task else task_id
    await db.execute(
        "INSERT INTO agent_runs (id, task_id, session_id, agent_name, tool, summary, "
        "outcome, status, started_at, completed_at, cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (id, full_task_id, session_id or None, agent_name, tool, summary,
         outcome or None, status, now, now, cost_usd),
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


async def insert_approval(db: aiosqlite.Connection, *, id: str,
                           task_id: str = "", requested_by: str,
                           reason: str, context: str = "") -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO approvals (id, task_id, requested_by, reason, context, requested_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (id, task_id or None, requested_by, reason, context or None, now),
    )
    await db.commit()


async def respond_approval(db: aiosqlite.Connection, *, approval_id: str,
                            status: str, response_note: str = "") -> None:
    now = time.time()
    await db.execute(
        "UPDATE approvals SET status = ?, response_note = ?, responded_at = ? "
        "WHERE id = ? OR id LIKE ?",
        (status, response_note or None, now, approval_id, f"{approval_id}%"),
    )
    await db.commit()


async def list_approvals(db: aiosqlite.Connection, status: str = "pending") -> list[dict]:
    async with db.execute(
        "SELECT * FROM approvals WHERE status = ? ORDER BY requested_at DESC", (status,)
    ) as cur:
        return [dict(r) async for r in cur]


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
