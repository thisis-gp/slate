from __future__ import annotations
from datetime import date, timedelta
from fastapi import APIRouter, Request
from slate.db.queries import get_daily_sync

router = APIRouter(tags=["sync"])

@router.get("/sync/daily")
async def daily_sync(request: Request, date_str: str = ""):
    d = date_str or date.today().isoformat()
    return await get_daily_sync(request.app.state.db, d)

@router.get("/sync/weekly")
async def weekly_sync(request: Request):
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    results = [await get_daily_sync(request.app.state.db, d) for d in days]
    return {
        "period": {"from": days[0], "to": days[-1]},
        "total_runs": sum(len(d["runs"]) for d in results),
        "total_cost_usd": sum(d["total_cost_usd"] for d in results),
        "days": results,
    }
