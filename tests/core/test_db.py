import pytest
import aiosqlite
from slate.db.schema import apply_schema

@pytest.mark.asyncio
async def test_schema_creates_all_tables():
    async with aiosqlite.connect(":memory:") as db:
        await apply_schema(db)
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ) as cur:
            tables = {row[0] async for row in cur}
    expected = {
        "projects", "tasks", "state_transitions", "sprints",
        "sessions", "agent_runs", "model_usage", "comments"
    }
    assert expected == tables


import uuid
from slate.db.queries import (
    insert_project, get_project, list_projects,
    insert_task, get_task, list_tasks, update_task_state,
    insert_agent_run, get_task_context,
    insert_session, end_session,
)

@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await apply_schema(conn)
        yield conn

@pytest.mark.asyncio
async def test_insert_and_get_project(db):
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="my-app")
    project = await get_project(db, pid)
    assert project["name"] == "my-app"
    assert project["status"] == "active"

@pytest.mark.asyncio
async def test_insert_and_move_task(db):
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="proj")
    tid = str(uuid.uuid4())
    await insert_task(db, id=tid, project_id=pid, title="Fix login bug",
                      type="bug", created_by="human")
    task = await get_task(db, tid)
    assert task["state"] == "todo"
    await update_task_state(db, task_id=tid, to_state="investigating",
                            changed_by="claude", reason="starting investigation")
    task = await get_task(db, tid)
    assert task["state"] == "investigating"

@pytest.mark.asyncio
async def test_get_task_context_includes_runs(db):
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="proj2")
    tid = str(uuid.uuid4())
    await insert_task(db, id=tid, project_id=pid, title="Research caching")
    rid = str(uuid.uuid4())
    await insert_agent_run(db, id=rid, task_id=tid, agent_name="claude",
                           tool="claude-code", summary="Researched Redis vs Memcached")
    ctx = await get_task_context(db, tid)
    assert ctx["task"]["title"] == "Research caching"
    assert len(ctx["runs"]) == 1
    assert ctx["runs"][0]["summary"] == "Researched Redis vs Memcached"

