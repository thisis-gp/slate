from __future__ import annotations
import asyncio
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slate.db.queries import (
    upsert_jira_config, get_jira_config, list_jira_sync_log, get_latest_pending,
    count_unlinked_worklogs, update_task_jira_key, get_task, list_pending_imports,
)
from slate.jira.sync import prepare_pending, approve_pending, reject_pending
from slate.jira.importer import (
    stage_assigned_issues, approve_import, reject_import, DEFAULT_JQL,
)
from slate.jira.scheduler import run_approval_scheduler

router = APIRouter(tags=["jira"])

DB_PATH = Path.home() / ".slate" / "db.sqlite"


class ConfigureRequest(BaseModel):
    base_url: str
    email: str
    api_token: str
    sync_time: str = "09:00"
    state_map: str = ""
    enabled: bool = True


@router.post("/jira/configure")
async def configure(body: ConfigureRequest, request: Request):
    await upsert_jira_config(
        request.app.state.db,
        base_url=body.base_url, email=body.email, api_token=body.api_token,
        sync_time=body.sync_time, state_map=body.state_map, enabled=body.enabled,
    )
    # Restart scheduler with new config
    if hasattr(request.app.state, "scheduler_task") and request.app.state.scheduler_task:
        request.app.state.scheduler_task.cancel()
    if body.enabled:
        request.app.state.scheduler_task = asyncio.create_task(
            run_approval_scheduler(body.sync_time, DB_PATH)
        )
    else:
        request.app.state.scheduler_task = None
    config = await get_jira_config(request.app.state.db)
    config.pop("api_token", None)
    return config


@router.get("/jira/status")
async def status(request: Request):
    config = await get_jira_config(request.app.state.db)
    if not config:
        raise HTTPException(status_code=404, detail="Jira not configured")
    config.pop("api_token", None)
    return config


@router.post("/jira/sync")
async def trigger_sync(request: Request):
    # Stages a pending batch for human approval — NEVER pushes directly.
    return await prepare_pending(request.app.state.db)


@router.post("/jira/preview")
async def preview(request: Request):
    result = await prepare_pending(request.app.state.db)
    result.setdefault("unlinked_count", await count_unlinked_worklogs(request.app.state.db))
    return result


@router.get("/jira/pending")
async def pending(request: Request):
    db = request.app.state.db
    unlinked = await count_unlinked_worklogs(db)
    row = await get_latest_pending(db)
    if not row:
        return {"pending": None, "unlinked_count": unlinked}
    row["batch"] = json.loads(row["batch_json"])
    row["unlinked_count"] = unlinked
    return row


class ApproveRequest(BaseModel):
    exclude: list[str] = []


@router.post("/jira/pending/{pending_id}/approve")
async def approve(pending_id: str, request: Request, body: ApproveRequest = ApproveRequest()):
    return await approve_pending(request.app.state.db, pending_id, exclude=body.exclude)


@router.post("/jira/pending/{pending_id}/reject")
async def reject(pending_id: str, request: Request):
    return await reject_pending(request.app.state.db, pending_id)


class LinkRequest(BaseModel):
    task_id: str
    jira_key: str


@router.post("/jira/link")
async def link(body: LinkRequest, request: Request):
    try:
        await update_task_jira_key(
            request.app.state.db, task_id=body.task_id, jira_key=body.jira_key
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await get_task(request.app.state.db, body.task_id)


class ImportRequest(BaseModel):
    jql: str = DEFAULT_JQL


@router.post("/jira/import")
async def jira_import(request: Request, body: ImportRequest = ImportRequest()):
    """Stage assigned Jira issues for approval. Creates NO tasks."""
    return await stage_assigned_issues(request.app.state.db, jql=body.jql)


@router.get("/jira/imports")
async def jira_imports(request: Request, status: str = "pending"):
    return await list_pending_imports(request.app.state.db, status=status)


class ImportApproveRequest(BaseModel):
    project_id: str
    assigned_to: str = ""
    write_obsidian: bool = True


@router.post("/jira/imports/{import_id}/approve")
async def jira_import_approve(import_id: str, body: ImportApproveRequest, request: Request):
    result = await approve_import(
        request.app.state.db, import_id, project_id=body.project_id,
        assigned_to=body.assigned_to, write_obsidian=body.write_obsidian,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/jira/imports/{import_id}/reject")
async def jira_import_reject(import_id: str, request: Request):
    result = await reject_import(request.app.state.db, import_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/jira/sync-log")
async def sync_log(request: Request, task_id: str = "", limit: int = 50):
    return await list_jira_sync_log(request.app.state.db, task_id=task_id, limit=limit)
