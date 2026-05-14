import pytest
import pytest_asyncio
import aiosqlite
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_task, get_task, update_task_status,
    insert_agent, get_agents_for_task,
    insert_cost_event, get_daily_cost,
)

@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.sqlite"
    async with aiosqlite.connect(db_path) as conn:
        await apply_schema(conn)
        yield conn

@pytest.mark.asyncio
async def test_insert_and_get_task(db):
    await insert_task(db, id="t1", prompt="fix the auth bug")
    task = await get_task(db, "t1")
    assert task["id"] == "t1"
    assert task["prompt"] == "fix the auth bug"
    assert task["status"] == "pending"

@pytest.mark.asyncio
async def test_update_task_status(db):
    await insert_task(db, id="t2", prompt="refactor db")
    await update_task_status(db, "t2", "running")
    task = await get_task(db, "t2")
    assert task["status"] == "running"

@pytest.mark.asyncio
async def test_insert_agent_and_list(db):
    await insert_task(db, id="t3", prompt="add tests")
    await insert_agent(db, id="a1", task_id="t3", role="sde1", model="llama", wave=1)
    agents = await get_agents_for_task(db, "t3")
    assert len(agents) == 1
    assert agents[0]["role"] == "sde1"

@pytest.mark.asyncio
async def test_cost_tracking(db):
    await insert_task(db, id="t4", prompt="refactor")
    await insert_agent(db, id="a2", task_id="t4", role="sde2", model="qwen", wave=1)
    await insert_cost_event(
        db, agent_id="a2", task_id="t4",
        model="qwen", provider="openrouter",
        input_tokens=100, output_tokens=50,
        cache_read_tokens=0, cost_usd=0.001,
    )
    total = await get_daily_cost(db)
    assert total == pytest.approx(0.001)
