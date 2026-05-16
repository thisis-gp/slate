from __future__ import annotations
import asyncio, uuid
import typer
from rich.console import Console
from rich.table import Table
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import list_approvals, respond_approval, insert_approval

app = typer.Typer(help="Human approval requests")
console = Console(legacy_windows=False)

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@app.command("request")
def request_cmd(
    reason: str = typer.Argument(...),
    task: str = typer.Option("", "--task", "-t"),
    by: str = typer.Option("agent", "--by"),
    context: str = typer.Option("", "--context", "-c"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            aid = str(uuid.uuid4())
            await insert_approval(db, id=aid, task_id=task, requested_by=by,
                                  reason=reason, context=context)
            console.print(f"[yellow]Approval requested[/] {aid[:8]} - {reason[:60]}")
    asyncio.run(_run())

@app.command("list")
def list_cmd(status: str = typer.Option("pending", "--status")):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            approvals = await list_approvals(db, status=status)
        table = Table("ID", "Task", "Requested By", "Reason", "Status")
        for a in approvals:
            table.add_row(a["id"][:8], (a["task_id"] or "")[:8],
                          a["requested_by"], a["reason"][:50], a["status"])
        console.print(table)
    asyncio.run(_run())

@app.command("approve")
def approve_cmd(approval_id: str = typer.Argument(...), note: str = typer.Option("", "--note")):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await respond_approval(db, approval_id=approval_id, status="approved", response_note=note)
            console.print(f"[green]Approved[/] {approval_id[:8]}")
    asyncio.run(_run())

@app.command("reject")
def reject_cmd(approval_id: str = typer.Argument(...), note: str = typer.Option("", "--note")):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await respond_approval(db, approval_id=approval_id, status="rejected", response_note=note)
            console.print(f"[red]Rejected[/] {approval_id[:8]}")
    asyncio.run(_run())
