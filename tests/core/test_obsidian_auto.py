"""The context loop: mutations refresh the Obsidian doc; freeform is surfaced."""
import uuid
import aiosqlite
import pytest
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_project, insert_task, update_task_jira_key, add_comment, insert_worklog,
    update_task_state,
)
from slate.obsidian.auto import refresh_doc_for_task, freeform_for_task
from slate.obsidian.vault import issue_doc_path


@pytest.fixture
async def task_with_jira(tmp_path, monkeypatch):
    monkeypatch.setenv("SLATE_VAULT_PATH", str(tmp_path))
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        await apply_schema(db)
        pid = str(uuid.uuid4())
        await insert_project(db, id=pid, name="proj")
        tid = str(uuid.uuid4())
        await insert_task(db, id=tid, project_id=pid, title="Build importer")
        await update_task_jira_key(db, task_id=tid, jira_key="BX-77")
        yield db, tid, tmp_path


async def test_refresh_writes_doc(task_with_jira):
    db, tid, vault = task_with_jira
    await add_comment(db, task_id=tid, author="codex", body="use SQLite", kind="decision")
    path = await refresh_doc_for_task(db, tid)
    assert path is not None
    doc = (vault / "slate" / "BX-77.md").read_text(encoding="utf-8")
    assert "use SQLite" in doc
    assert "Build importer" in doc


async def test_no_jira_key_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SLATE_VAULT_PATH", str(tmp_path))
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        await apply_schema(db)
        pid = str(uuid.uuid4())
        await insert_project(db, id=pid, name="p")
        tid = str(uuid.uuid4())
        await insert_task(db, id=tid, project_id=pid, title="no jira")
        assert await refresh_doc_for_task(db, tid) is None


async def test_no_vault_is_noop_and_safe(task_with_jira, monkeypatch):
    db, tid, _ = task_with_jira
    monkeypatch.delenv("SLATE_VAULT_PATH", raising=False)
    # No vault configured anywhere → returns None, never raises.
    assert await refresh_doc_for_task(db, tid, subfolder="slate") is None


async def test_freeform_preserved_and_surfaced(task_with_jira):
    db, tid, vault = task_with_jira
    await refresh_doc_for_task(db, tid)
    p = vault / "slate" / "BX-77.md"
    text = p.read_text(encoding="utf-8") + "\nHand-written design note: prefer claim-then-push.\n"
    p.write_text(text, encoding="utf-8")

    # A later mutation refreshes the managed block but keeps the freeform note.
    await update_task_state(db, task_id=tid, to_state="in_progress", changed_by="guru")
    await refresh_doc_for_task(db, tid)

    ff = await freeform_for_task(db, tid)
    assert ff is not None
    assert "prefer claim-then-push" in ff
    # managed-block content should NOT appear in freeform
    assert "SLATE:BEGIN" not in ff


async def test_refresh_after_worklog_and_state(task_with_jira):
    db, tid, vault = task_with_jira
    await insert_worklog(db, id=str(uuid.uuid4()), task_id=tid,
                         agent_name="cursor", tool="cli", summary="parsed the file",
                         time_spent_seconds=600)
    await update_task_state(db, task_id=tid, to_state="code_review", changed_by="guru")
    await refresh_doc_for_task(db, tid)
    doc = (vault / "slate" / "BX-77.md").read_text(encoding="utf-8")
    assert "parsed the file" in doc
    assert "code_review" in doc
