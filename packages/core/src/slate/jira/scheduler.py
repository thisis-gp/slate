from __future__ import annotations
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import aiosqlite
from slate.db.schema import apply_schema
from slate.db.queries import get_scheduler_last_run, set_scheduler_last_run
from slate.jira.sync import sync_all, sync_worklogs_all, prepare_pending
from slate.jira.importer import stage_assigned_issues

DB_PATH = Path.home() / ".slate" / "db.sqlite"
DEFAULT_TZ = "Asia/Kolkata"
POLL_SECONDS = 60


def _tz() -> ZoneInfo:
    """Scheduler timezone. Env SLATE_TZ overrides; defaults to Asia/Kolkata.

    The container runs in UTC, so without this a '09:00' sync would fire at
    09:00 UTC (14:30 IST). zoneinfo data ships via the ``tzdata`` dependency, so
    this resolves the same on slim Linux images and on Windows.
    """
    name = os.getenv("SLATE_TZ", DEFAULT_TZ)
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def parse_sync_time(sync_time: str) -> tuple[int, int]:
    try:
        parts = sync_time.split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 9, 0


def _seconds_until(hour: int, minute: int) -> float:
    """Naive local seconds until the next HH:MM. Kept for backward-compat/tests.

    Prefer the date-stamped poll loop below for production scheduling — this
    helper has no missed-run recovery.
    """
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_daily(
    name: str,
    sync_time: str,
    db_path: Path,
    action,
    *,
    poll_seconds: int = POLL_SECONDS,
) -> None:
    """Fire ``action(db)`` once per local day at/after ``sync_time``.

    Polls every ``poll_seconds`` and stamps the run date in ``scheduler_state``,
    so a window missed while the process was down fires on the next startup
    (catch-up) and never fires twice the same day.
    """
    hour, minute = parse_sync_time(sync_time)
    tz = _tz()
    print(f"[scheduler:{name}] started for {hour:02d}:{minute:02d} {tz.key}", flush=True)
    while True:
        try:
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                await apply_schema(db)
                last = await get_scheduler_last_run(db, name)
                if now >= due and last != today:
                    print(f"[scheduler:{name}] firing for {today}", flush=True)
                    result = await action(db)
                    await set_scheduler_last_run(db, name, today)
                    print(f"[scheduler:{name}] result: {result}", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            import traceback
            print(f"[scheduler:{name}] tick failed", flush=True)
            traceback.print_exc()
        await asyncio.sleep(poll_seconds)


async def run_approval_scheduler(sync_time: str = "09:00", db_path: Path = DB_PATH) -> None:
    """Daily: stage a pending sync batch for human approval (NO push to Jira)."""
    await _run_daily("approval", sync_time, db_path, prepare_pending)


async def run_scheduler(sync_time: str = "09:00", db_path: Path = DB_PATH) -> None:
    """Daily status-transition sync. NOTE: bypasses the approval gate — not wired
    into the API lifespan by default; use only if you want auto state pushes."""
    await _run_daily("status", sync_time, db_path, sync_all)


async def run_worklog_scheduler(sync_time: str = "11:00", db_path: Path = DB_PATH) -> None:
    """Daily worklog push. NOTE: bypasses the approval gate — not wired into the
    API lifespan by default; the approval scheduler is the supported path."""
    await _run_daily("worklog", sync_time, db_path, sync_worklogs_all)


async def run_import_scheduler(sync_time: str = "08:30", db_path: Path = DB_PATH) -> None:
    """Daily: stage Jira issues assigned to you for approval (creates NO tasks).

    Approval-gated like the worklog flow — this only fills the import queue; you
    assign each issue to a project and approve it in the UI/CLI."""
    await _run_daily("import", sync_time, db_path, stage_assigned_issues)
