from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slate.db.queries import upsert_jira_config, get_jira_config, list_jira_sync_log
from slate.jira.sync import sync_all

router = APIRouter(tags=["jira"])


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
    return await get_jira_config(request.app.state.db)


@router.get("/jira/status")
async def status(request: Request):
    config = await get_jira_config(request.app.state.db)
    if not config:
        raise HTTPException(status_code=404, detail="Jira not configured")
    return config


@router.post("/jira/sync")
async def trigger_sync(request: Request):
    return await sync_all(request.app.state.db)


@router.get("/jira/sync-log")
async def sync_log(request: Request, task_id: str = "", limit: int = 50):
    return await list_jira_sync_log(request.app.state.db, task_id=task_id, limit=limit)
