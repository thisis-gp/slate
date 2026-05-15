from __future__ import annotations
import uuid
from datetime import date
from fastapi import APIRouter, Request
from pydantic import BaseModel
from slate.db.queries import insert_session, end_session

router = APIRouter(tags=["sessions"])

class StartSessionRequest(BaseModel):
    agent_name: str
    tool: str = ""
    project_id: str = ""

class EndSessionRequest(BaseModel):
    summary: str = ""
    total_cost_usd: float = 0.0

@router.post("/sessions", status_code=201)
async def start_session(body: StartSessionRequest, request: Request):
    sid = str(uuid.uuid4())
    await insert_session(request.app.state.db, id=sid, agent_name=body.agent_name,
                          tool=body.tool, project_id=body.project_id,
                          date=date.today().isoformat())
    return {"id": sid, **body.model_dump()}

@router.post("/sessions/{session_id}/end")
async def finish_session(session_id: str, body: EndSessionRequest, request: Request):
    await end_session(request.app.state.db, session_id=session_id,
                       summary=body.summary, total_cost_usd=body.total_cost_usd)
    return {"id": session_id, "status": "ended"}
