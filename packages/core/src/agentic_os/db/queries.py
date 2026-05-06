from __future__ import annotations
import time
from typing import Any
import aiosqlite


async def insert_task(conn: aiosqlite.Connection, *, id: str, prompt: str) -> None:
    await conn.execute(
        "INSERT INTO tasks (id, prompt, created_at) VALUES (?, ?, ?)",
        (id, prompt, time.time()),
    )
    await conn.commit()


async def get_task(conn: aiosqlite.Connection, task_id: str) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_task_status(
    conn: aiosqlite.Connection, task_id: str, status: str
) -> None:
    completed_at = time.time() if status in ("done", "failed") else None
    await conn.execute(
        "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
        (status, completed_at, task_id),
    )
    await conn.commit()


async def insert_agent(
    conn: aiosqlite.Connection,
    *,
    id: str,
    task_id: str,
    role: str,
    model: str,
    wave: int,
) -> None:
    await conn.execute(
        "INSERT INTO agents (id, task_id, role, model, wave) VALUES (?, ?, ?, ?, ?)",
        (id, task_id, role, model, wave),
    )
    await conn.commit()


async def get_agents_for_task(
    conn: aiosqlite.Connection, task_id: str
) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    async with conn.execute(
        "SELECT * FROM agents WHERE task_id = ? ORDER BY wave, role", (task_id,)
    ) as cur:
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def insert_cost_event(
    conn: aiosqlite.Connection,
    *,
    agent_id: str,
    task_id: str,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cost_usd: float,
) -> None:
    await conn.execute(
        """INSERT INTO cost_events
           (agent_id, task_id, model, provider, input_tokens, output_tokens,
            cache_read_tokens, cost_usd, ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (agent_id, task_id, model, provider, input_tokens, output_tokens,
         cache_read_tokens, cost_usd, time.time()),
    )
    await conn.commit()


async def get_daily_cost(conn: aiosqlite.Connection) -> float:
    day_start = time.time() - 86400
    async with conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_events WHERE ts >= ?",
        (day_start,),
    ) as cur:
        row = await cur.fetchone()
        return float(row[0]) if row else 0.0
