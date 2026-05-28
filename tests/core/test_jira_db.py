import pytest
import uuid
import aiosqlite
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_project, insert_task, insert_agent_run,
    upsert_jira_config, get_jira_config,
    list_tasks_with_jira, update_task_jira_key,
    insert_jira_sync_log, get_unsynced_runs,
)

@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await apply_schema(conn)
        yield conn

@pytest.fixture
async def project_and_task(db):
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="myproject", key="MP")
    tid = str(uuid.uuid4())
    await insert_task(db, id=tid, project_id=pid, title="Fix login")
    return pid, tid

@pytest.mark.asyncio
async def test_schema_includes_jira_tables(db):
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ) as cur:
        tables = {row[0] async for row in cur}
    assert "jira_config" in tables
    assert "jira_sync_log" in tables

@pytest.mark.asyncio
async def test_tasks_has_jira_issue_key_column(db):
    async with db.execute("PRAGMA table_info(tasks)") as cur:
        cols = {row[1] async for row in cur}
    assert "jira_issue_key" in cols

@pytest.mark.asyncio
async def test_upsert_and_get_jira_config(db):
    await upsert_jira_config(db, base_url="https://myorg.atlassian.net",
                              email="dev@myorg.com", api_token="secret123",
                              sync_time="09:00")
    cfg = await get_jira_config(db)
    assert cfg["base_url"] == "https://myorg.atlassian.net"
    assert cfg["email"] == "dev@myorg.com"
    assert cfg["sync_time"] == "09:00"
    assert cfg["enabled"] == 1

@pytest.mark.asyncio
async def test_upsert_jira_config_is_idempotent(db):
    await upsert_jira_config(db, base_url="https://a.atlassian.net",
                              email="a@a.com", api_token="tok1")
    await upsert_jira_config(db, base_url="https://b.atlassian.net",
                              email="b@b.com", api_token="tok2", sync_time="21:00")
    cfg = await get_jira_config(db)
    assert cfg["base_url"] == "https://b.atlassian.net"
    assert cfg["sync_time"] == "21:00"

@pytest.mark.asyncio
async def test_get_jira_config_returns_none_when_empty(db):
    cfg = await get_jira_config(db)
    assert cfg is None

@pytest.mark.asyncio
async def test_list_tasks_with_jira_only_returns_linked(db, project_and_task):
    pid, tid = project_and_task
    tid2 = str(uuid.uuid4())
    await insert_task(db, id=tid2, project_id=pid, title="No jira link")
    await update_task_jira_key(db, task_id=tid, jira_key="PROJ-42")
    tasks = await list_tasks_with_jira(db)
    assert len(tasks) == 1
    assert tasks[0]["jira_issue_key"] == "PROJ-42"

@pytest.mark.asyncio
async def test_get_unsynced_runs_excludes_already_synced(db, project_and_task):
    pid, tid = project_and_task
    rid1 = str(uuid.uuid4())
    rid2 = str(uuid.uuid4())
    await insert_agent_run(db, id=rid1, task_id=tid, agent_name="claude",
                           tool="claude-code", summary="Run 1")
    await insert_agent_run(db, id=rid2, task_id=tid, agent_name="claude",
                           tool="claude-code", summary="Run 2")
    await insert_jira_sync_log(db, task_id=tid, jira_key="PROJ-42",
                                action="worklog", status="ok", run_id=rid1)
    runs = await get_unsynced_runs(db, tid, "PROJ-42")
    assert len(runs) == 1
    assert runs[0]["id"] == rid2
