from fastapi import APIRouter, Request
from agentic_os.db.queries import get_daily_cost

router = APIRouter()


@router.get("/costs/today")
async def costs_today(request: Request):
    db = request.app.state.db
    total = await get_daily_cost(db)
    return {"cost_usd": round(total, 6), "period": "24h"}
