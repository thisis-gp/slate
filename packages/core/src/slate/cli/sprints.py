from __future__ import annotations
import asyncio
import uuid
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_sprint, get_sprint, list_sprints,
    update_sprint_status, assign_task_to_sprint, get_sprint_tasks,
    get_project,
)

app = typer.Typer(help="Manage sprints")
console = Console(legacy_windows=False)

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@app.command("create")
def create_sprint(
    name: str = typer.Argument(...),
    project: str = typer.Option(..., "--project", "-p"),
    goal: str = typer.Option("", "--goal", "-g"),
    start: str = typer.Option("", "--start", help="YYYY-MM-DD"),
    end: str = typer.Option("", "--end", help="YYYY-MM-DD"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            sid = str(uuid.uuid4())
            await insert_sprint(db, id=sid, project_id=project, name=name,
                                goal=goal, start_date=start, end_date=end)
            console.print(f"[green]Created sprint[/] [bold]{name}[/] ({sid[:8]})")
    asyncio.run(_run())

@app.command("list")
def list_cmd(
    project: str = typer.Option("", "--project", "-p"),
    status: str = typer.Option("", "--status", "-s"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            sprints = await list_sprints(db, project_id=project, status=status)
        if not sprints:
            console.print("[dim]No sprints found.[/]")
            return
        table = Table("ID", "Name", "Status", "Goal", "Start", "End")
        for s in sprints:
            goal_preview = (s["goal"] or "")[:40]
            table.add_row(s["id"][:8], s["name"], s["status"],
                          goal_preview, s["start_date"] or "-", s["end_date"] or "-")
        console.print(table)
    asyncio.run(_run())

@app.command("show")
def show_sprint(sprint_id: str = typer.Argument(...)):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            sprint = await get_sprint(db, sprint_id)
            if not sprint:
                console.print("[red]Sprint not found[/]")
                return
            tasks = await get_sprint_tasks(db, sprint_id)
            proj = await get_project(db, sprint["project_id"])
            proj_key = proj["key"] if proj and proj.get("key") else ""
        body = (
            f"[bold]{sprint['name']}[/]\n"
            f"Status: [yellow]{sprint['status']}[/]   "
            f"Start: {sprint['start_date'] or '-'}   End: {sprint['end_date'] or '-'}\n"
        )
        if sprint.get("goal"):
            body += f"Goal: {sprint['goal']}\n"
        console.print(Panel(body, title=f"Sprint {sprint['id'][:8]}"))
        if tasks:
            console.print(f"\n[bold]Tasks ({len(tasks)}):[/]")
            table = Table("Ticket", "Title", "State", "Assignee", "Pts")
            for t in tasks:
                num = t["number"] or ""
                ticket = f"{proj_key}-{num}" if proj_key and num else t["id"][:8]
                pts = str(t["story_points"]) if t.get("story_points") else "-"
                table.add_row(ticket, t["title"][:50], t["state"],
                              t["assigned_to"] or "-", pts)
            console.print(table)
        else:
            console.print("[dim]No tasks assigned to this sprint.[/]")
    asyncio.run(_run())

@app.command("start")
def start_sprint(sprint_id: str = typer.Argument(...)):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await update_sprint_status(db, sprint_id, "active")
            console.print(f"[green]Sprint {sprint_id[:8]} started[/]")
    asyncio.run(_run())

@app.command("complete")
def complete_sprint(sprint_id: str = typer.Argument(...)):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await update_sprint_status(db, sprint_id, "completed")
            console.print(f"[green]Sprint {sprint_id[:8]} completed[/]")
    asyncio.run(_run())

@app.command("assign")
def assign_task(
    task_id: str = typer.Argument(...),
    sprint_id: str = typer.Argument(...),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await assign_task_to_sprint(db, task_id=task_id, sprint_id=sprint_id)
            console.print(f"[green]Task {task_id[:8]} assigned to sprint {sprint_id[:8]}[/]")
    asyncio.run(_run())
