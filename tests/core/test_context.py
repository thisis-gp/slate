import uuid
import aiosqlite
import pytest
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_project, insert_task, add_comment, insert_worklog, get_task_context,
)


@pytest.fixture
async def setup():
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        await apply_schema(db)
        pid = str(uuid.uuid4())
        await insert_project(db, id=pid, name="ctx-proj")
        tid = str(uuid.uuid4())
        await insert_task(db, id=tid, project_id=pid, title="Build importer")
        yield db, tid


async def test_comment_kinds_split_in_context(setup):
    db, tid = setup
    await add_comment(db, task_id=tid, author="claude", body="picked SQLite over PG", kind="decision")
    await add_comment(db, task_id=tid, author="codex", body="parser wired, tests next", kind="heartbeat")
    await add_comment(db, task_id=tid, author="guru", body="looks good", kind="note")

    ctx = await get_task_context(db, tid)
    assert len(ctx["decisions"]) == 1
    assert ctx["decisions"][0]["body"] == "picked SQLite over PG"
    assert len(ctx["heartbeats"]) == 1
    assert ctx["latest_heartbeat"]["body"] == "parser wired, tests next"
    assert len(ctx["notes"]) == 1
    assert ctx["notes"][0]["body"] == "looks good"
    # all three still present in the flat comments list
    assert len(ctx["comments"]) == 3


async def test_latest_heartbeat_is_most_recent(setup):
    db, tid = setup
    await add_comment(db, task_id=tid, author="a", body="step 1", kind="heartbeat")
    await add_comment(db, task_id=tid, author="a", body="step 2", kind="heartbeat")
    ctx = await get_task_context(db, tid)
    assert ctx["latest_heartbeat"]["body"] == "step 2"


async def test_default_kind_is_note(setup):
    db, tid = setup
    c = await add_comment(db, task_id=tid, author="x", body="hi")
    assert c["kind"] == "note"
