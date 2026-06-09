import asyncio
import aiosqlite
import pytest
from slate.db.schema import apply_schema
from slate.db.queries import get_scheduler_last_run, set_scheduler_last_run
from slate.jira import scheduler


@pytest.fixture
async def db_file(tmp_path):
    path = tmp_path / "sched.sqlite"
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await apply_schema(db)
    return path


async def test_scheduler_state_roundtrip(db_file):
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        await apply_schema(db)
        assert await get_scheduler_last_run(db, "approval") is None
        await set_scheduler_last_run(db, "approval", "2026-06-08")
        assert await get_scheduler_last_run(db, "approval") == "2026-06-08"
        # upsert overwrites, no duplicate row
        await set_scheduler_last_run(db, "approval", "2026-06-09")
        assert await get_scheduler_last_run(db, "approval") == "2026-06-09"


async def test_overdue_window_fires_once_then_dedupes(db_file):
    """A window that is already past (and never ran today) fires immediately
    on startup — the missed-run recovery — and does not fire again same day."""
    calls = []

    async def action(db):
        calls.append(1)
        return {"ok": True}

    task = asyncio.create_task(
        scheduler._run_daily(
            "approval", "00:00", db_file, action, poll_seconds=0.05
        )
    )
    await asyncio.sleep(0.3)  # several poll ticks
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(calls) == 1  # recovered + fired exactly once, not per-tick
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        assert await get_scheduler_last_run(db, "approval") is not None


async def test_import_scheduler_uses_independent_state(db_file):
    """The import scheduler tracks its own last-run date, independent of approval."""
    calls = []

    async def action(db):
        calls.append(1)

    task = asyncio.create_task(
        scheduler._run_daily("import", "00:00", db_file, action, poll_seconds=0.05)
    )
    await asyncio.sleep(0.25)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(calls) == 1
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        assert await get_scheduler_last_run(db, "import") is not None
        assert await get_scheduler_last_run(db, "approval") is None  # independent
