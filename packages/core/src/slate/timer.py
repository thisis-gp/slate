"""Work timers behind ``slate timer start/stop``.

An agent starts a timer when it begins work on a ticket and stops it with a
summary when it finishes. The stop writes one worklog whose time is the real
wall-clock time minus pauses, so Jira time is measured rather than guessed.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Optional

import aiosqlite

from slate.db.queries import get_task, insert_worklog
from slate.jira.scrub import worklog_problems

# A stop above this is almost always a timer left running overnight.
MAX_UNATTENDED_SECONDS = 10 * 3600
_JIRA_KEY_RE = re.compile(r"^[A-Za-z]+-\d+$")


class TimerError(Exception):
    """A timer action that cannot be done; the message says why and what to do."""


async def resolve_task(db: aiosqlite.Connection, ref: str) -> Optional[dict]:
    """Find a task by Jira key (BX-4270) first, then by slate id or ticket."""
    ref = ref.strip()
    if _JIRA_KEY_RE.match(ref):
        async with db.execute(
            "SELECT * FROM tasks WHERE jira_issue_key = ? ORDER BY created_at DESC LIMIT 1",
            (ref.upper(),),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
    return await get_task(db, ref)


def elapsed_seconds(timer: dict, now: Optional[float] = None) -> int:
    end = timer.get("paused_at") or timer.get("stopped_at") or (now or time.time())
    return max(0, int(end - timer["started_at"] - (timer.get("paused_seconds") or 0)))


async def active_timers(db: aiosqlite.Connection, agent: str = "") -> list[dict]:
    sql = (
        "SELECT tm.*, t.jira_issue_key, t.title AS task_title FROM timers tm "
        "LEFT JOIN tasks t ON t.id = tm.task_id WHERE tm.status IN ('running', 'paused')"
    )
    params: tuple = ()
    if agent:
        sql += " AND tm.agent_name = ?"
        params = (agent,)
    async with db.execute(sql + " ORDER BY tm.started_at", params) as cur:
        return [dict(r) async for r in cur]


async def active_timer(db: aiosqlite.Connection, agent: str) -> Optional[dict]:
    rows = await active_timers(db, agent)
    return rows[0] if rows else None


def label(timer: dict) -> str:
    return timer.get("jira_issue_key") or timer["task_id"][:8]


async def start(db: aiosqlite.Connection, ref: str, agent: str, tool: str = "cli",
                now: Optional[float] = None) -> tuple[dict, bool]:
    """Start a timer. Returns (timer, created). The same task again is a no-op."""
    now = now or time.time()
    task = await resolve_task(db, ref)
    if not task:
        raise TimerError(
            f"no slate task for {ref}. Create or link one first: "
            f"slate task create ... --jira {ref}  or  slate jira link <task> {ref}")
    if not task.get("jira_issue_key"):
        raise TimerError(
            f"task {ref} has no BX ticket linked, so its time can never reach Jira. "
            f"Link it: slate jira link {task['id'][:8]} BX-<n>")
    current = await active_timer(db, agent)
    if current:
        if current["task_id"] == task["id"]:
            if current["status"] == "paused":
                current = await resume(db, agent, now)
            return current, False
        raise TimerError(
            f"{agent} already has a timer on {label(current)} "
            f"({elapsed_seconds(current, now) // 60}m). Stop it first: "
            f'slate timer stop "<summary>" --agent {agent}')
    await db.execute(
        "INSERT INTO timers (id, task_id, agent_name, tool, started_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), task["id"], agent, tool, now),
    )
    await db.commit()
    return await active_timer(db, agent), True


async def pause(db: aiosqlite.Connection, agent: str, now: Optional[float] = None) -> dict:
    now = now or time.time()
    t = await active_timer(db, agent)
    if not t:
        raise TimerError(f"no running timer for {agent}")
    if t["status"] == "running":
        await db.execute("UPDATE timers SET status = 'paused', paused_at = ? WHERE id = ?",
                         (now, t["id"]))
        await db.commit()
    return await active_timer(db, agent)


async def resume(db: aiosqlite.Connection, agent: str, now: Optional[float] = None) -> dict:
    now = now or time.time()
    t = await active_timer(db, agent)
    if not t:
        raise TimerError(f"no paused timer for {agent}")
    if t["status"] == "paused":
        await db.execute(
            "UPDATE timers SET status = 'running', paused_seconds = paused_seconds + ?, "
            "paused_at = NULL WHERE id = ?",
            (max(0.0, now - t["paused_at"]), t["id"]),
        )
        await db.commit()
    return await active_timer(db, agent)


async def _close(db: aiosqlite.Connection, t: dict, status: str, now: float,
                 worklog_id: Optional[str]) -> None:
    paused_extra = (now - t["paused_at"]) if t.get("paused_at") else 0
    await db.execute(
        "UPDATE timers SET status = ?, stopped_at = ?, worklog_id = ?, "
        "paused_seconds = paused_seconds + ?, paused_at = NULL WHERE id = ?",
        (status, now, worklog_id, paused_extra, t["id"]),
    )
    await db.commit()


async def stop(db: aiosqlite.Connection, agent: str, summary: str = "", *,
               minutes: int = 0, discard: bool = False, force: bool = False,
               now: Optional[float] = None) -> dict:
    """Stop the agent's timer and write its worklog (unless ``discard``).

    ``minutes`` overrides the measured time and is required when the measured
    time exceeds ``MAX_UNATTENDED_SECONDS``. ``force`` skips the summary check.
    """
    now = now or time.time()
    t = await active_timer(db, agent)
    if not t:
        raise TimerError(
            f"no running timer for {agent}. Start one: slate timer start BX-<n> --agent {agent}")
    measured = elapsed_seconds(t, now)
    if discard:
        await _close(db, t, "discarded", now, None)
        return {**t, "status": "discarded", "seconds": measured, "worklog_id": None}
    if not force:
        problems = worklog_problems(summary)
        if problems:
            raise TimerError("summary rejected: " + "; ".join(problems))
    if minutes <= 0 and measured > MAX_UNATTENDED_SECONDS:
        raise TimerError(
            f"timer on {label(t)} has run {measured // 3600}h{measured % 3600 // 60:02d}m, "
            f"which looks left running. Pass the real time: --time <minutes>")
    seconds = minutes * 60 if minutes > 0 else measured
    wid = str(uuid.uuid4())
    await insert_worklog(db, id=wid, task_id=t["task_id"], agent_name=agent, tool=t["tool"],
                         summary=summary.strip(), time_spent_seconds=seconds,
                         started_at=t["started_at"])
    await _close(db, t, "stopped", now, wid)
    return {**t, "status": "stopped", "seconds": max(60, seconds), "worklog_id": wid}
