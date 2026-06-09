import pytest
import asyncio
import uuid
import aiosqlite
from unittest.mock import AsyncMock, patch
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_project, insert_task, insert_agent_run,
    upsert_jira_config, update_task_jira_key,
    list_jira_sync_log, insert_worklog, list_worklogs,
    mark_worklog_synced, get_pending,
)
from slate.jira.sync import (
    sync_all,
    _sync_status,
    _sync_worklogs_legacy as _sync_worklogs,
    prepare_pending,
    approve_pending,
)
from slate.jira.client import JiraClient
from slate.jira.mapping import DEFAULT_STATE_MAP
import slate.jira.sync as jira_sync


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await apply_schema(conn)
        yield conn


@pytest.fixture
async def setup(db):
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="myproject")
    tid = str(uuid.uuid4())
    await insert_task(db, id=tid, project_id=pid, title="Fix login")
    await update_task_jira_key(db, task_id=tid, jira_key="PROJ-42")
    await upsert_jira_config(db, base_url="https://myorg.atlassian.net",
                              email="dev@myorg.com", api_token="secret")
    return pid, tid


@pytest.mark.asyncio
async def test_sync_all_skipped_when_no_config(db):
    result = await sync_all(db)
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_sync_all_skipped_when_disabled(db):
    await upsert_jira_config(db, base_url="https://x.atlassian.net",
                              email="a@b.com", api_token="tok", enabled=False)
    result = await sync_all(db)
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_sync_status_transitions_when_mapping_found(db, setup):
    pid, tid = setup
    async with db.execute("SELECT * FROM tasks WHERE id = ?", (tid,)) as cur:
        task = dict(await cur.fetchone())
    task["state"] = "in_progress"

    client = AsyncMock(spec=JiraClient)
    client.get_transitions.return_value = [
        {"id": "11", "name": "Start", "to": {"name": "In Progress"}},
    ]
    client.transition_issue = AsyncMock()

    result = await _sync_status(db, client, task, DEFAULT_STATE_MAP)
    assert result["ok"] is True
    assert result["transitioned_to"] == "In Progress"
    client.transition_issue.assert_called_once_with("PROJ-42", "11")


@pytest.mark.asyncio
async def test_sync_status_logs_approval_needed_when_transition_missing(db, setup):
    pid, tid = setup
    async with db.execute("SELECT * FROM tasks WHERE id = ?", (tid,)) as cur:
        task = dict(await cur.fetchone())
    task["state"] = "done"

    client = AsyncMock(spec=JiraClient)
    client.get_transitions.return_value = [
        {"id": "5", "name": "Reopen", "to": {"name": "Open"}},
    ]

    result = await _sync_status(db, client, task, DEFAULT_STATE_MAP)
    assert result["skipped"] is True
    logs = await list_jira_sync_log(db)
    assert any(l["status"] == "approval_needed" for l in logs)


@pytest.mark.asyncio
async def test_sync_status_skips_when_no_state_mapping(db, setup):
    pid, tid = setup
    async with db.execute("SELECT * FROM tasks WHERE id = ?", (tid,)) as cur:
        task = dict(await cur.fetchone())
    task["state"] = "unknown_state"

    client = AsyncMock(spec=JiraClient)
    result = await _sync_status(db, client, task, DEFAULT_STATE_MAP)
    assert result["skipped"] is True
    client.get_transitions.assert_not_called()


@pytest.mark.asyncio
async def test_sync_worklogs_pushes_unsynced_runs(db, setup):
    pid, tid = setup
    rid = str(uuid.uuid4())
    await insert_agent_run(db, id=rid, task_id=tid, agent_name="claude",
                           tool="claude-code", summary="Fixed the bug")

    client = AsyncMock(spec=JiraClient)
    client.add_worklog.return_value = {"id": "50001"}

    result = await _sync_worklogs(db, client, tid, "PROJ-42")
    assert result["synced_worklogs"] == 1
    client.add_worklog.assert_called_once()
    call_kwargs = client.add_worklog.call_args[1]
    assert "Fixed the bug" in call_kwargs["comment"]
    assert "claude" not in call_kwargs["comment"].lower()
    assert "claude-code" not in call_kwargs["comment"].lower()


@pytest.mark.asyncio
async def test_sync_worklogs_skips_already_synced_runs(db, setup):
    pid, tid = setup
    rid = str(uuid.uuid4())
    await insert_agent_run(db, id=rid, task_id=tid, agent_name="claude",
                           tool="claude-code", summary="Already done")
    from slate.db.queries import insert_jira_sync_log
    await insert_jira_sync_log(db, task_id=tid, jira_key="PROJ-42",
                                action="worklog", status="ok", run_id=rid)

    client = AsyncMock(spec=JiraClient)
    result = await _sync_worklogs(db, client, tid, "PROJ-42")
    assert result["synced_worklogs"] == 0
    client.add_worklog.assert_not_called()


@pytest.mark.asyncio
async def test_sync_all_returns_synced_count(db, setup):
    pid, tid = setup
    client_mock = AsyncMock(spec=JiraClient)
    client_mock.get_transitions.return_value = [
        {"id": "11", "name": "In Progress", "to": {"name": "In Progress"}},
    ]
    client_mock.add_worklog.return_value = {"id": "99"}

    with patch("slate.jira.sync.JiraClient", return_value=client_mock):
        result = await sync_all(db)

    assert result["synced"] == 1


@pytest.mark.asyncio
async def test_approval_pushes_worklog_without_checking_transitions(db, setup):
    pid, tid = setup
    await insert_worklog(
        db,
        id=str(uuid.uuid4()),
        task_id=tid,
        agent_name="codex",
        tool="codex",
        summary="Implemented the fix",
        time_spent_seconds=1800,
    )
    pending = await prepare_pending(db)

    client = AsyncMock(spec=JiraClient)
    client.get_transitions.side_effect = AssertionError("transitions must not be checked")
    client.transition_issue.side_effect = AssertionError("transitions must not be pushed")
    client.add_worklog.return_value = {"id": "50002"}

    with patch("slate.jira.sync.JiraClient", return_value=client):
        result = await approve_pending(db, pending["pending_id"])

    assert result["failed"] == 0
    assert result["pushed"] == 1
    client.get_transitions.assert_not_called()
    client.transition_issue.assert_not_called()
    client.add_worklog.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_pending_formats_entries_as_user_work(db, setup):
    pid, tid = setup
    await insert_worklog(
        db,
        id=str(uuid.uuid4()),
        task_id=tid,
        agent_name="claude",
        tool="claude-code",
        summary="Implemented the fix",
        time_spent_seconds=1800,
    )

    pending = await prepare_pending(db)

    entries = pending["batch"]["issues"][0]["entries"]
    assert entries == ["Implemented the fix"]


@pytest.mark.asyncio
async def test_approval_skips_worklogs_already_synced_elsewhere(db, setup):
    pid, tid = setup
    wid = str(uuid.uuid4())
    await insert_worklog(
        db,
        id=wid,
        task_id=tid,
        agent_name="codex",
        tool="codex",
        summary="Implemented the fix",
        time_spent_seconds=1800,
    )
    pending = await prepare_pending(db)
    await mark_worklog_synced(db, wid, "already-synced")

    client = AsyncMock(spec=JiraClient)
    with patch("slate.jira.sync.JiraClient", return_value=client):
        result = await approve_pending(db, pending["pending_id"])

    assert result["pushed"] == 0
    assert result["failed"] == 0
    assert result["results"] == [{"jira_key": "PROJ-42", "status": "skipped", "reason": "already synced"}]
    client.add_worklog.assert_not_called()


@pytest.mark.asyncio
async def test_approval_supersedes_older_pending_batches_for_same_worklogs(db, setup):
    pid, tid = setup
    await insert_worklog(
        db,
        id=str(uuid.uuid4()),
        task_id=tid,
        agent_name="codex",
        tool="codex",
        summary="Implemented the fix",
        time_spent_seconds=1800,
    )
    older = await prepare_pending(db)
    newer = await prepare_pending(db)

    client = AsyncMock(spec=JiraClient)
    client.add_worklog.return_value = {"id": "50003"}
    with patch("slate.jira.sync.JiraClient", return_value=client):
        result = await approve_pending(db, newer["pending_id"])

    older_row = await get_pending(db, older["pending_id"])
    newer_row = await get_pending(db, newer["pending_id"])
    assert result["pushed"] == 1
    assert older_row["status"] == "superseded"
    assert newer_row["status"] == "pushed"


@pytest.mark.asyncio
async def test_prepare_pending_falls_back_when_summary_times_out(db, setup, monkeypatch):
    pid, tid = setup
    await insert_worklog(
        db,
        id=str(uuid.uuid4()),
        task_id=tid,
        agent_name="codex",
        tool="codex",
        summary="Implemented the fix",
        time_spent_seconds=1800,
    )

    async def slow_summary(*args, **kwargs):
        await asyncio.sleep(1)
        return "too slow", "slow"

    monkeypatch.setattr(jira_sync, "SUMMARY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(jira_sync, "summarize_worklog", slow_summary)

    pending = await prepare_pending(db)

    issue = pending["batch"]["issues"][0]
    assert pending["pending_id"]
    assert issue["summary_provider"] == "concat_timeout"
    assert "Implemented the fix" in issue["summary"]


@pytest.mark.asyncio
async def test_approval_exclude_marks_worklogs_handled(db, setup):
    pid, tid = setup
    wid = str(uuid.uuid4())
    await insert_worklog(
        db,
        id=wid,
        task_id=tid,
        agent_name="codex",
        tool="codex",
        summary="Do not push this",
        time_spent_seconds=900,
    )
    pending = await prepare_pending(db)

    result = await approve_pending(db, pending["pending_id"], exclude=["PROJ-42"])

    logs = await list_worklogs(db, task_id=tid)
    sync_logs = await list_jira_sync_log(db, task_id=tid)
    assert result["results"] == [{"jira_key": "PROJ-42", "status": "excluded"}]
    assert logs[0]["synced_to_jira"] == 1
    assert logs[0]["jira_worklog_id"] == f"excluded:{pending['pending_id']}"
    assert sync_logs[0]["status"] == "excluded"
