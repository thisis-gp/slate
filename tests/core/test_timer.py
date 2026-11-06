import uuid

import aiosqlite
import pytest

from slate import timer as timers
from slate.db.queries import insert_project, insert_task, update_task_jira_key, list_worklogs
from slate.db.schema import apply_schema
from slate.jira.scrub import worklog_problems

GOOD = "Fixed null org_entity_id crash in the ecard handler; added regression test, PR #7801"
T0 = 1_800_000_000.0


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await apply_schema(conn)
        yield conn


@pytest.fixture
async def tasks(db):
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="nova")
    ids = []
    for key in ("BX-4270", "BX-4271"):
        tid = str(uuid.uuid4())
        await insert_task(db, id=tid, project_id=pid, title=f"Task {key}")
        await update_task_jira_key(db, task_id=tid, jira_key=key)
        ids.append(tid)
    unlinked = str(uuid.uuid4())
    await insert_task(db, id=unlinked, project_id=pid, title="No ticket")
    return ids + [unlinked]


@pytest.mark.asyncio
async def test_start_resolves_by_jira_key_and_stop_logs_measured_time(db, tasks):
    t, created = await timers.start(db, "bx-4270", "claude", "claude-code", now=T0)
    assert created and t["task_id"] == tasks[0]
    r = await timers.stop(db, "claude", GOOD, now=T0 + 47 * 60)
    assert r["seconds"] == 47 * 60
    [w] = await list_worklogs(db, task_id=tasks[0])
    assert w["time_spent_seconds"] == 47 * 60
    assert w["started_at"] == T0
    assert w["summary"] == GOOD
    assert await timers.active_timer(db, "claude") is None


@pytest.mark.asyncio
async def test_pause_time_is_not_logged(db, tasks):
    await timers.start(db, "BX-4270", "claude", now=T0)
    await timers.pause(db, "claude", now=T0 + 600)
    await timers.resume(db, "claude", now=T0 + 600 + 3600)
    r = await timers.stop(db, "claude", GOOD, now=T0 + 600 + 3600 + 300)
    assert r["seconds"] == 900


@pytest.mark.asyncio
async def test_stop_while_paused_excludes_the_pause(db, tasks):
    await timers.start(db, "BX-4270", "claude", now=T0)
    await timers.pause(db, "claude", now=T0 + 1200)
    r = await timers.stop(db, "claude", GOOD, now=T0 + 9000)
    assert r["seconds"] == 1200


@pytest.mark.asyncio
async def test_start_same_ticket_is_noop_and_other_ticket_refused(db, tasks):
    await timers.start(db, "BX-4270", "claude", now=T0)
    t, created = await timers.start(db, "BX-4270", "claude", now=T0 + 60)
    assert not created and t["started_at"] == T0
    with pytest.raises(timers.TimerError, match="already has a timer on BX-4270"):
        await timers.start(db, "BX-4271", "claude", now=T0 + 120)
    # another agent can time another ticket at the same time
    _, created = await timers.start(db, "BX-4271", "codex", now=T0 + 120)
    assert created


@pytest.mark.asyncio
async def test_start_refuses_unknown_or_unlinked_task(db, tasks):
    with pytest.raises(timers.TimerError, match="no slate task"):
        await timers.start(db, "BX-9999", "claude")
    with pytest.raises(timers.TimerError, match="no BX ticket"):
        await timers.start(db, tasks[2], "claude")


@pytest.mark.asyncio
async def test_bad_summary_rejected_and_timer_keeps_running(db, tasks):
    await timers.start(db, "BX-4270", "claude", now=T0)
    for bad in ["Checked PR status and CI state", "Claude fixed the login redirect bug today",
                "done", "Reviewed the comments"]:
        with pytest.raises(timers.TimerError, match="summary rejected"):
            await timers.stop(db, "claude", bad, now=T0 + 600)
    assert await timers.active_timer(db, "claude") is not None
    r = await timers.stop(db, "claude", "done", force=True, now=T0 + 600)
    assert r["status"] == "stopped"


@pytest.mark.asyncio
async def test_long_timer_needs_explicit_time(db, tasks):
    await timers.start(db, "BX-4270", "claude", now=T0)
    with pytest.raises(timers.TimerError, match="looks left running"):
        await timers.stop(db, "claude", GOOD, now=T0 + 11 * 3600)
    r = await timers.stop(db, "claude", GOOD, minutes=95, now=T0 + 11 * 3600)
    assert r["seconds"] == 95 * 60


@pytest.mark.asyncio
async def test_discard_writes_no_worklog(db, tasks):
    await timers.start(db, "BX-4270", "claude", now=T0)
    r = await timers.stop(db, "claude", discard=True, now=T0 + 600)
    assert r["status"] == "discarded"
    assert await list_worklogs(db, task_id=tasks[0]) == []
    assert await timers.active_timer(db, "claude") is None


def test_worklog_problems_accepts_house_format():
    assert worklog_problems(GOOD) == []
    assert worklog_problems(
        "Built per-campaign email personalisation via Claude, gated on anthropic_api_key") == []
    assert worklog_problems("I fixed the login redirect for retail users")  # first person
