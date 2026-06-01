from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import aiosqlite
from slate.db.schema import apply_schema
from slate.jira.sync import sync_all, sync_worklogs_all, prepare_pending

DB_PATH = Path.home() / ".slate" / "db.sqlite"


def parse_sync_time(sync_time: str) -> tuple[int, int]:
    try:
        parts = sync_time.split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 9, 0


def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_scheduler(sync_time: str = "09:00", db_path: Path = DB_PATH) -> None:
    hour, minute = parse_sync_time(sync_time)
    while True:
        await asyncio.sleep(_seconds_until(hour, minute))
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await sync_all(db)


async def run_worklog_scheduler(sync_time: str = "11:00", db_path: Path = DB_PATH) -> None:
    hour, minute = parse_sync_time(sync_time)
    while True:
        await asyncio.sleep(_seconds_until(hour, minute))
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await sync_worklogs_all(db)


async def run_approval_scheduler(sync_time: str = "09:00", db_path: Path = DB_PATH) -> None:
    """Daily: stage a pending sync batch for human approval (NO push to Jira)."""
    hour, minute = parse_sync_time(sync_time)
    while True:
        await asyncio.sleep(_seconds_until(hour, minute))
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await prepare_pending(db)
