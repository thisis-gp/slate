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
        "sessions", "agent_runs", "model_usage", "comments", "approvals"
    }
    assert expected == tables
