from __future__ import annotations
import asyncio
from datetime import date, timedelta
import typer
from rich.console import Console
from rich.panel import Panel
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import get_daily_sync

app = typer.Typer(help="Generate sync reports")
console = Console()

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@app.command("daily")
def daily(target_date: str = typer.Option("", "--date", "-d")):
    d = target_date or date.today().isoformat()
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            data = await get_daily_sync(db, d)
        console.print(Panel(
            f"[bold]Daily Sync — {data['date']}[/]\n\n"
            f"Sessions: {len(data['sessions'])}  Runs: {len(data['runs'])}  "
            f"Transitions: {len(data['transitions'])}  Cost: [yellow]${data['total_cost_usd']:.4f}[/]",
            title="Daily Sync"
        ))
    asyncio.run(_run())

@app.command("weekly")
def weekly():
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            today = date.today()
            days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
            all_data = [await get_daily_sync(db, d) for d in days]
        total_runs = sum(len(d["runs"]) for d in all_data)
        total_cost = sum(d["total_cost_usd"] for d in all_data)
        console.print(Panel(
            f"[bold]Weekly Sync — {days[0]} to {days[-1]}[/]\n\n"
            f"Total runs: {total_runs}  Cost: [yellow]${total_cost:.4f}[/]",
            title="Weekly Sync"
        ))
    asyncio.run(_run())
