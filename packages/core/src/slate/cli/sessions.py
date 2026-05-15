from __future__ import annotations
import asyncio, uuid
from datetime import date as dt
import typer
from rich.console import Console
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import insert_session, end_session

app = typer.Typer(help="Manage agent sessions")
console = Console()

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@app.command("start")
def start_session(
    agent: str = typer.Argument(...),
    tool: str = typer.Option("", "--tool", "-t"),
    project: str = typer.Option("", "--project", "-p"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            sid = str(uuid.uuid4())
            await insert_session(db, id=sid, agent_name=agent, tool=tool,
                                 project_id=project, date=dt.today().isoformat())
            console.print(f"[green]Started session[/] for {agent}\nSession ID: {sid}")
    asyncio.run(_run())

@app.command("end")
def end_session_cmd(
    session_id: str = typer.Argument(...),
    summary: str = typer.Option("", "--summary", "-s"),
    cost: float = typer.Option(0.0, "--cost", "-c"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await end_session(db, session_id=session_id, summary=summary, total_cost_usd=cost)
            console.print(f"[green]Ended session[/] {session_id[:8]}")
    asyncio.run(_run())
