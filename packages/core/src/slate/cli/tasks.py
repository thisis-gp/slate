from __future__ import annotations
import asyncio, uuid
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import insert_task, list_tasks, get_task_context, update_task_state

app = typer.Typer(help="Manage tasks")
console = Console()

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@app.command("create")
def create_task(
    title: str = typer.Argument(...),
    project: str = typer.Option(..., "--project", "-p"),
    description: str = typer.Option("", "--desc", "-d"),
    type: str = typer.Option("feature", "--type", "-t"),
    priority: str = typer.Option("medium", "--priority"),
    assigned_to: str = typer.Option("", "--assign", "-a"),
    parent: str = typer.Option("", "--parent"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            tid = str(uuid.uuid4())
            await insert_task(db, id=tid, project_id=project, title=title,
                              description=description, type=type, priority=priority,
                              assigned_to=assigned_to, parent_task_id=parent)
            console.print(f"[green]Created task[/] [bold]{title}[/] ({tid[:8]})")
    asyncio.run(_run())

@app.command("list")
def list_task(
    project: str = typer.Option("", "--project", "-p"),
    state: str = typer.Option("", "--state", "-s"),
    assigned_to: str = typer.Option("", "--assign", "-a"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            tasks = await list_tasks(db, project_id=project, state=state, assigned_to=assigned_to)
        table = Table("ID", "Title", "State", "Priority", "Assigned To", "Type")
        for t in tasks:
            table.add_row(t["id"][:8], t["title"], t["state"],
                          t["priority"], t["assigned_to"] or "—", t["type"])
        console.print(table)
    asyncio.run(_run())

@app.command("show")
def show_task(task_id: str = typer.Argument(...)):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            ctx = await get_task_context(db, task_id)
        task = ctx["task"]
        console.print(Panel(
            f"[bold]{task['title']}[/]\nState: [yellow]{task['state']}[/]  "
            f"Priority: {task['priority']}  Type: {task['type']}\n"
            f"Assigned to: {task['assigned_to'] or '—'}\n\n{task['description'] or ''}",
            title=f"Task {task_id[:8]}"
        ))
        if ctx["runs"]:
            console.print("\n[bold]Agent Runs:[/]")
            for r in ctx["runs"]:
                console.print(f"  [{r['tool']}] {r['agent_name']}: {r['summary']}")
        if ctx["transitions"]:
            console.print("\n[bold]State History:[/]")
            for t in ctx["transitions"]:
                console.print(f"  {t['from_state'] or '—'} → {t['to_state']} by {t['changed_by']}")
    asyncio.run(_run())

@app.command("move")
def move_task(
    task_id: str = typer.Argument(...),
    state: str = typer.Argument(...),
    by: str = typer.Option("human", "--by"),
    reason: str = typer.Option("", "--reason"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await update_task_state(db, task_id=task_id, to_state=state,
                                    changed_by=by, reason=reason)
            console.print(f"[green]Moved[/] {task_id[:8]} → [bold]{state}[/]")
    asyncio.run(_run())
