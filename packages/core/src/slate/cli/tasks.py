from __future__ import annotations
import asyncio, uuid, json
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import insert_task, list_tasks, get_task_context, update_task_state

app = typer.Typer(help="Manage tasks")
console = Console(legacy_windows=False)

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
    reporter: str = typer.Option("", "--reporter", "-r"),
    parent: str = typer.Option("", "--parent"),
    points: int = typer.Option(0, "--points"),
    labels: str = typer.Option("", "--labels", help="Comma-separated e.g. auth,backend"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            tid = str(uuid.uuid4())
            labels_json = json.dumps([l.strip() for l in labels.split(",") if l.strip()]) if labels else ""
            await insert_task(db, id=tid, project_id=project, title=title,
                              description=description, type=type, priority=priority,
                              assigned_to=assigned_to, reporter=reporter,
                              parent_task_id=parent, story_points=points,
                              labels=labels_json)
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
            # Build project key map
            async with db.execute("SELECT id, key FROM projects") as cur:
                proj_keys = {r["id"]: r["key"] or "" async for r in cur}
        table = Table("Ticket", "ID", "Title", "State", "Priority", "Assigned To", "Pts")
        for t in tasks:
            key = proj_keys.get(t["project_id"], "")
            num = t["number"] or ""
            ticket = f"{key}-{num}" if key and num else t["id"][:8]
            pts = str(t["story_points"]) if t["story_points"] else "-"
            table.add_row(ticket, t["id"][:8], t["title"], t["state"],
                          t["priority"], t["assigned_to"] or "-", pts)
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
        if not task:
            console.print("[red]Task not found[/]")
            return
        ticket = task["id"][:8]
        labels_str = ""
        if task.get("labels"):
            try:
                labels_str = ", ".join(json.loads(task["labels"]))
            except Exception:
                labels_str = task["labels"]
        pts = str(task["story_points"]) if task.get("story_points") else "-"
        body = (
            f"[bold]{task['title']}[/]\n"
            f"State: [yellow]{task['state']}[/]  Priority: {task['priority']}  "
            f"Type: {task['type']}  Points: {pts}\n"
            f"Assignee: {task['assigned_to'] or '-'}  Reporter: {task.get('reporter') or '-'}\n"
        )
        if labels_str:
            body += f"Labels: {labels_str}\n"
        if task.get("description"):
            body += f"\n{task['description']}"
        console.print(Panel(body, title=f"Task {ticket}"))
        if ctx["transitions"]:
            console.print("\n[bold]State History:[/]")
            for t in ctx["transitions"]:
                frm = t["from_state"] or "-"
                assign_note = f" -> {t['new_assignee']}" if t.get("new_assignee") else ""
                console.print(f"  {frm} -> {t['to_state']} by {t['changed_by']}{assign_note}")
        if ctx["runs"]:
            console.print("\n[bold]Agent Runs:[/]")
            for r in ctx["runs"]:
                cost = f" ${r['cost_usd']:.4f}" if r.get("cost_usd") else ""
                commit = f"\n    commit {r['commit_sha'][:8]} {r['commit_message'][:72]}" if r.get("commit_sha") else ""
                console.print(f"  [{r['tool']}] {r['agent_name']}: {r['summary'][:80]}{cost}{commit}")
        if ctx["comments"]:
            console.print("\n[bold]Comments:[/]")
            for c in ctx["comments"]:
                console.print(f"  [{c['author_type']}] {c['author']}: {c['body']}")
    asyncio.run(_run())

@app.command("move")
def move_task(
    task_id: str = typer.Argument(...),
    state: str = typer.Argument(...),
    by: str = typer.Option("human", "--by"),
    reason: str = typer.Option("", "--reason"),
    assign: str = typer.Option("", "--assign"),
):
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await update_task_state(db, task_id=task_id, to_state=state,
                                    changed_by=by, reason=reason, new_assignee=assign)
            suffix = f" -> {assign}" if assign else ""
            console.print(f"[green]Moved[/] {task_id[:8]} -> [bold]{state}[/]{suffix}")
    asyncio.run(_run())
