from __future__ import annotations
import asyncio
import typer
from rich.console import Console
from rich.table import Table
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import add_comment, list_comments

app = typer.Typer(help="Task comments")
console = Console(legacy_windows=False)

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@app.command("add")
def add_cmd(
    task_id: str = typer.Argument(...),
    body: str = typer.Argument(...),
    by: str = typer.Option("human", "--by"),
    author_type: str = typer.Option("human", "--type"),
    kind: str = typer.Option("note", "--kind", "-k",
                             help="note | decision | heartbeat"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await add_comment(db, task_id=task_id, author=by, body=body,
                              author_type=author_type, kind=kind)
            from slate.obsidian.auto import refresh_doc_for_task
            await refresh_doc_for_task(db, task_id)
            label = "Decision" if kind == "decision" else "Comment"
            console.print(f"[green]{label} added[/] to {task_id}")
    asyncio.run(_run())

@app.command("decision")
def decision_cmd(
    task_id: str = typer.Argument(...),
    body: str = typer.Argument(..., help="The decision and its rationale"),
    by: str = typer.Option("human", "--by"),
    author_type: str = typer.Option("agent", "--type"),
):
    """Record a decision taken on a task (shortcut for `comment add --kind decision`).

    Agents should call this whenever they make a non-trivial call so the next
    agent (or you) sees *why*, not just *what*.
    """
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await add_comment(db, task_id=task_id, author=by, body=body,
                              author_type=author_type, kind="decision")
            from slate.obsidian.auto import refresh_doc_for_task
            await refresh_doc_for_task(db, task_id)
            console.print(f"[green]Decision recorded[/] on {task_id}")
    asyncio.run(_run())

@app.command("list")
def list_cmd(
    task_id: str = typer.Argument(...),
    kind: str = typer.Option("", "--kind", "-k", help="Filter: note|decision|heartbeat"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            comments = await list_comments(db, task_id)
        if kind:
            comments = [c for c in comments if c.get("kind", "note") == kind]
        if not comments:
            console.print("[dim]No comments yet.[/]")
            return
        table = Table("Author", "Kind", "Comment", "Time")
        for c in comments:
            ts = str(round(c["ts"])) if c.get("ts") else "-"
            body_preview = c["body"][:80]
            table.add_row(c["author"], c.get("kind", "note"), body_preview, ts)
        console.print(table)
    asyncio.run(_run())
