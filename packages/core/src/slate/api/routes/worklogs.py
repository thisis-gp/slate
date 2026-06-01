from __future__ import annotations
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slate.db.queries import (
    insert_worklog, list_worklogs, get_task,
    mark_worklog_synced, get_unsynced_worklogs,
    get_jira_config, insert_jira_sync_log,
)
from slate.jira.client import JiraClient
from slate.jira.mapping import format_worklog_started
from collections import defaultdict

router = APIRouter(tags=["worklogs"])


class CreateWorklogRequest(BaseModel):
    task_id: str
    summary: str
    agent_name: str = "agent"
    tool: str = "api"
    time_spent_seconds: int = 1800
    agent_run_id: str = ""


class SyncWorklogsResponse(BaseModel):
    synced: int
    failed: int
    details: list[dict]


@router.post("/worklogs", status_code=201)
async def create_worklog(body: CreateWorklogRequest, request: Request):
    task = await get_task(request.app.state.db, body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    wid = str(uuid.uuid4())
    await insert_worklog(
        request.app.state.db, id=wid, task_id=body.task_id,
        agent_run_id=body.agent_run_id, agent_name=body.agent_name,
        tool=body.tool, summary=body.summary,
        time_spent_seconds=body.time_spent_seconds,
    )
    return {"id": wid, **body.model_dump()}


@router.get("/worklogs")
async def get_worklogs(request: Request, task_id: str = "", pending: bool = False):
    return await list_worklogs(
        request.app.state.db, task_id=task_id,
        unsynced_only=pending,
    )


@router.post("/worklogs/sync")
async def sync_worklogs(request: Request, dry_run: bool = False):
    config = await get_jira_config(request.app.state.db)
    if not config or not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Jira not configured")

    client = JiraClient(
        base_url=config["base_url"],
        email=config["email"],
        api_token=config["api_token"],
    )

    logs = await get_unsynced_worklogs(request.app.state.db)
    if not logs:
        return {"synced": 0, "failed": 0, "details": [], "message": "No pending worklogs"}

    by_jira = defaultdict(list)
    for log in logs:
        jira_key = log.get("jira_issue_key")
        if jira_key:
            by_jira[jira_key].append(log)

    if dry_run:
        details = []
        for jira_key, items in by_jira.items():
            total_mins = sum(w["time_spent_seconds"] for w in items) // 60
            details.append({"jira_key": jira_key, "entries": len(items), "minutes": total_mins})
        return {"synced": 0, "failed": 0, "details": details, "dry_run": True}

    synced = 0
    failed = 0
    details = []

    for jira_key, items in by_jira.items():
        total_seconds = sum(w["time_spent_seconds"] for w in items)
        total_mins = total_seconds // 60

        summaries = []
        for w in items:
            summaries.append(f"[{w['tool']}] {w['agent_name']}: {w['summary']}")
        combined_summary = "\n".join(summaries[:10])
        if len(summaries) > 10:
            combined_summary += f"\n... and {len(summaries) - 10} more entries"

        started_ts = min(w["started_at"] for w in items)

        try:
            result = await client.add_worklog(
                jira_key,
                time_spent_seconds=max(60, total_seconds),
                comment=combined_summary,
                started=format_worklog_started(started_ts),
            )
            jira_wid = result.get("id", "")

            for w in items:
                await mark_worklog_synced(request.app.state.db, w["id"], jira_wid)
                await insert_jira_sync_log(
                    request.app.state.db, task_id=w["task_id"], jira_key=jira_key,
                    action="worklog", status="ok",
                    detail=f"Aggregated {len(items)} entries, {total_mins}m",
                )

            synced += 1
            details.append({"jira_key": jira_key, "status": "ok", "entries": len(items), "minutes": total_mins})
        except Exception as e:
            failed += 1
            details.append({"jira_key": jira_key, "status": "error", "error": str(e)[:200]})
            for w in items:
                await insert_jira_sync_log(
                    request.app.state.db, task_id=w["task_id"], jira_key=jira_key,
                    action="worklog", status="error",
                    detail=str(e)[:200],
                )

    return {"synced": synced, "failed": failed, "details": details}
