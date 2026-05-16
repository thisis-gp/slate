from __future__ import annotations
import uuid
from fastapi import APIRouter, Request
from pydantic import BaseModel
from slate.db.queries import insert_agent_run

router = APIRouter(tags=["runs"])

class LogRunRequest(BaseModel):
    task_id: str
    agent_name: str
    tool: str
    summary: str
    outcome: str = ""
    status: str = "completed"
    cost_usd: float = 0.0
    session_id: str = ""
    commit_sha: str = ""
    commit_message: str = ""

@router.post("/runs", status_code=201)
async def log_run(body: LogRunRequest, request: Request):
    rid = str(uuid.uuid4())
    await insert_agent_run(request.app.state.db, id=rid, **body.model_dump())
    return {"id": rid, **body.model_dump()}
