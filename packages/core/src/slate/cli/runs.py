from __future__ import annotations
import asyncio, uuid
import typer
from rich.console import Console
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import insert_agent_run

app = typer.Typer(help="Log agent runs")
console = Console(legacy_windows=False)

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@app.command("log")
def log_run(
    task_id: str = typer.Argument(...),
    summary: str = typer.Argument(...),
    agent: str = typer.Option("human", "--agent", "-a"),
    tool: str = typer.Option("human", "--tool", "-t"),
    outcome: str = typer.Option("", "--outcome", "-o"),
    cost: float = typer.Option(0.0, "--cost", "-c"),
    session: str = typer.Option("", "--session", "-s"),
    status: str = typer.Option("completed", "--status"),
    commit: str = typer.Option("", "--commit", help="Git commit SHA"),
    commit_msg: str = typer.Option("", "--commit-msg", help="Git commit message"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            rid = str(uuid.uuid4())
            await insert_agent_run(db, id=rid, task_id=task_id, agent_name=agent,
                                   tool=tool, summary=summary, outcome=outcome,
                                   status=status, cost_usd=cost, session_id=session,
                                   commit_sha=commit, commit_message=commit_msg)
            suffix = f" commit [{commit[:8]}]" if commit else ""
            console.print(f"[green]Logged run[/] on {task_id[:8]} by [bold]{agent}[/]{suffix}")
    asyncio.run(_run())
