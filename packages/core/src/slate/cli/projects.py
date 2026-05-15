from __future__ import annotations
import asyncio, uuid
import typer
from rich.console import Console
from rich.table import Table
from slate.db.schema import apply_schema
from slate.db.queries import insert_project, list_projects
import aiosqlite
from pathlib import Path

app = typer.Typer(help="Manage projects")
console = Console()

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@app.command("create")
def create_project(
    name: str = typer.Argument(..., help="Project name"),
    description: str = typer.Option("", "--desc", "-d"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            pid = str(uuid.uuid4())
            await insert_project(db, id=pid, name=name, description=description)
            console.print(f"[green]Created project[/] [bold]{name}[/] ({pid})")
    asyncio.run(_run())

@app.command("list")
def list_project():
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            projects = await list_projects(db)
        table = Table("ID", "Name", "Description", "Status")
        for p in projects:
            table.add_row(p["id"][:8], p["name"], p["description"] or "", p["status"])
        console.print(table)
    asyncio.run(_run())
