import pytest
import aiosqlite
from slate.db.schema import apply_schema
from slate.mcp import tools

@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await apply_schema(conn)
        yield conn

@pytest.mark.asyncio
async def test_create_project_tool(db):
    result = await tools.create_project(db, name="test-project")
    assert result["name"] == "test-project"
    assert "id" in result

@pytest.mark.asyncio
async def test_full_task_lifecycle(db):
    p = await tools.create_project(db, name="proj")
    t = await tools.create_task(db, project_id=p["id"], title="Implement login",
                                 type="feature", created_by="orchestrator")
    assert t["state"] == "todo"
    updated = await tools.update_task_state(db, task_id=t["id"],
                                             to_state="implementing",
                                             changed_by="claude-code")
    assert updated["state"] == "implementing"
    await tools.log_agent_run(db, task_id=t["id"], agent_name="claude",
                               tool="claude-code", summary="Implemented JWT auth")
    ctx = await tools.get_task_context(db, t["id"])
    assert ctx["task"]["state"] == "implementing"
    assert len(ctx["runs"]) == 1

@pytest.mark.asyncio
async def test_list_tasks_tool(db):
    p = await tools.create_project(db, name="proj3")
    await tools.create_task(db, project_id=p["id"], title="Task A")
    await tools.create_task(db, project_id=p["id"], title="Task B")
    tasks = await tools.list_tasks_tool(db, project_id=p["id"])
    assert len(tasks) == 2
