import uuid
import aiosqlite
import pytest
from unittest.mock import AsyncMock, patch
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_project, upsert_jira_config, list_pending_imports,
    task_exists_for_jira_key, get_task,
)
from slate.jira import importer


def _issue(key, summary="Do the thing", itype="Bug", priority="High", status="To Do"):
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "issuetype": {"name": itype},
            "priority": {"name": priority},
            "status": {"name": status},
        },
    }


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await apply_schema(conn)
        await upsert_jira_config(conn, base_url="https://x.atlassian.net",
                                 email="a@b.com", api_token="t", sync_time="09:00")
        yield conn


@pytest.fixture
async def project(db):
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="slate-repo", key="BX")
    return pid


async def test_stage_only_creates_no_tasks(db, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_PREFIXES", "BX")
    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-1"), _issue("BX-2")])):
        result = await importer.stage_assigned_issues(db)
    assert result["staged_count"] == 2
    assert not await task_exists_for_jira_key(db, "BX-1")  # nothing created yet
    pending = await list_pending_imports(db)
    assert {p["jira_key"] for p in pending} == {"BX-1", "BX-2"}


async def test_non_bx_keys_skipped(db, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_PREFIXES", "BX")
    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-1"), _issue("AB-9")])):
        result = await importer.stage_assigned_issues(db)
    assert result["staged"] == ["BX-1"]
    assert any(s["jira_key"] == "AB-9" for s in result["skipped"])


async def test_idempotent_restage(db, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_PREFIXES", "BX")
    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-1")])):
        await importer.stage_assigned_issues(db)
        result = await importer.stage_assigned_issues(db)
    assert result["staged_count"] == 0  # already pending, not duplicated
    assert len(await list_pending_imports(db)) == 1


async def test_approve_creates_linked_task(db, project, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_PREFIXES", "BX")
    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-7", summary="Fix login",
                                                         itype="Bug", priority="Highest")])):
        await importer.stage_assigned_issues(db)
    [pending] = await list_pending_imports(db)

    result = await importer.approve_import(db, pending["id"], project_id=project,
                                           assigned_to="guru", write_obsidian=False)
    assert "error" not in result
    task = await get_task(db, result["task_id"])
    assert task["jira_issue_key"] == "BX-7"
    assert task["title"] == "Fix login"
    assert task["type"] == "bug"
    assert task["priority"] == "critical"  # Highest -> critical
    assert task["assigned_to"] == "guru"
    # no longer pending
    assert await list_pending_imports(db) == []
    assert await list_pending_imports(db, status="imported")


async def test_reject_removes_from_pending(db, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_PREFIXES", "BX")
    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-3")])):
        await importer.stage_assigned_issues(db)
    [pending] = await list_pending_imports(db)
    await importer.reject_import(db, pending["id"])
    assert await list_pending_imports(db) == []
    assert await list_pending_imports(db, status="rejected")


async def test_already_imported_key_skipped_on_restage(db, project, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_PREFIXES", "BX")
    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-5")])):
        await importer.stage_assigned_issues(db)
    [pending] = await list_pending_imports(db)
    await importer.approve_import(db, pending["id"], project_id=project, write_obsidian=False)

    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-5")])):
        result = await importer.stage_assigned_issues(db)
    assert result["staged_count"] == 0
    assert any(s["reason"] == "already imported" for s in result["skipped"])
