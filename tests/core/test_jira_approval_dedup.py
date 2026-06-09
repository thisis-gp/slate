"""Duplicate-prevention guarantees for the approval push path (gaps A & B)."""
import asyncio
import uuid
import json
import aiosqlite
import pytest
from unittest.mock import AsyncMock, patch
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_project, insert_task, update_task_jira_key, upsert_jira_config,
    insert_worklog, list_worklogs, get_pending,
    claim_worklogs_for_push, release_worklog_claims, finalize_worklog_claims,
    release_stale_worklog_claims,
)
from slate.jira import sync as jira_sync
from slate.jira.sync import prepare_pending, approve_pending


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await apply_schema(conn)
        yield conn


@pytest.fixture
async def staged(db):
    """A project/task with one Jira-linked worklog, staged into a pending batch."""
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="proj")
    tid = str(uuid.uuid4())
    await insert_task(db, id=tid, project_id=pid, title="Fix login")
    await update_task_jira_key(db, task_id=tid, jira_key="BX-42")
    await upsert_jira_config(db, base_url="https://x.atlassian.net",
                             email="a@b.com", api_token="t", sync_time="09:00")
    await insert_worklog(db, id=str(uuid.uuid4()), task_id=tid,
                         agent_name="codex", tool="cli", summary="did the work",
                         time_spent_seconds=1800)
    res = await prepare_pending(db)
    return tid, res["pending_id"]


# ── claim primitive ───────────────────────────────────────────────────────────

async def test_claim_is_exclusive(db, staged):
    _tid, _pid = staged
    [w] = await list_worklogs(db, unsynced_only=True)
    first = await claim_worklogs_for_push(db, [w["id"]], "claiming:A")
    second = await claim_worklogs_for_push(db, [w["id"]], "claiming:B")
    assert len(first) == 1            # A got it
    assert second == []               # B saw it already claimed → zero rows


async def test_release_only_touches_token(db, staged):
    _tid, _pid = staged
    [w] = await list_worklogs(db, unsynced_only=True)
    await claim_worklogs_for_push(db, [w["id"]], "claiming:A")
    await finalize_worklog_claims(db, [w["id"]], "9999")   # simulate successful push
    released = await release_worklog_claims(db, "claiming:A")
    assert released == 0              # finalized rows are NOT reverted
    rows = await list_worklogs(db, synced_only=True)
    assert rows[0]["jira_worklog_id"] == "9999"


# ── gap A: concurrent overlapping approvals push exactly once ──────────────────

async def test_concurrent_approvals_push_once(db, staged):
    _tid, pid = staged
    # A second pending batch over the SAME worklog (overlapping).
    res2 = await prepare_pending(db)
    pid2 = res2["pending_id"]
    assert pid2 and pid2 != pid

    calls = []

    async def slow_add_worklog(key, **kw):
        calls.append(key)
        await asyncio.sleep(0.05)     # widen the race window
        return {"id": f"jira-{len(calls)}"}

    with patch.object(jira_sync.JiraClient, "add_worklog",
                      new=AsyncMock(side_effect=slow_add_worklog)):
        r1, r2 = await asyncio.gather(
            approve_pending(db, pid),
            approve_pending(db, pid2),
        )

    # Exactly one real Jira push for the shared worklog.
    assert len(calls) == 1
    total_pushed = (r1.get("pushed", 0) or 0) + (r2.get("pushed", 0) or 0)
    assert total_pushed == 1
    synced = await list_worklogs(db, synced_only=True)
    assert len(synced) == 1
    assert synced[0]["jira_worklog_id"] == "jira-1"


# ── gap B: a failed push releases the claim so it retries (no silent loss) ──────

async def test_failed_push_releases_claim(db, staged):
    _tid, pid = staged
    with patch.object(jira_sync.JiraClient, "add_worklog",
                      new=AsyncMock(side_effect=RuntimeError("jira 500"))):
        r = await approve_pending(db, pid)
    assert r["failed"] == 1
    # The worklog must be unsynced again, ready for the next batch.
    assert len(await list_worklogs(db, unsynced_only=True)) == 1
    assert len(await list_worklogs(db, synced_only=True)) == 0


async def test_stale_claim_recovered_not_recent(db, staged):
    """A claim left by a crash (between claim and push) is recovered when old,
    but a fresh in-flight claim is left alone."""
    _tid, _pid = staged
    [w] = await list_worklogs(db, unsynced_only=True)
    await claim_worklogs_for_push(db, [w["id"]], "claiming:crashed")

    # Recent claim: sweeper with a long cutoff leaves it (push may be in flight).
    assert await release_stale_worklog_claims(db, older_than_seconds=600) == 0
    assert len(await list_worklogs(db, unsynced_only=True)) == 0

    # Treat it as stale (cutoff in the future) → recovered to unsynced.
    assert await release_stale_worklog_claims(db, older_than_seconds=-1) == 1
    assert len(await list_worklogs(db, unsynced_only=True)) == 1


async def test_successful_push_marks_synced_with_real_id(db, staged):
    _tid, pid = staged
    with patch.object(jira_sync.JiraClient, "add_worklog",
                      new=AsyncMock(return_value={"id": "55501"})):
        r = await approve_pending(db, pid)
    assert r["pushed"] == 1
    synced = await list_worklogs(db, synced_only=True)
    assert len(synced) == 1
    assert synced[0]["jira_worklog_id"] == "55501"
    assert len(await list_worklogs(db, unsynced_only=True)) == 0
