from __future__ import annotations
import asyncio, uuid, json
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import insert_task, list_tasks, get_task_context, update_task_state, add_comment

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
    jira: str = typer.Option("", "--jira", help="Jira issue key e.g. PROJ-123"),
):
    """Create a new task. If --jira is not provided, you will be prompted for it."""
    # Interactive Jira prompt if not provided
    if not jira:
        jira_input = typer.prompt("Jira issue key (e.g. PROJ-123) or press Enter to skip", default="")
        jira = jira_input.strip()

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
                              labels=labels_json, jira_issue_key=jira)
            jira_note = f" linked to [cyan]{jira.upper()}[/]" if jira else ""
            console.print(f"[green]Created task[/] [bold]{title}[/] ({tid[:8]}){jira_note}")
    try:
        asyncio.run(_run())
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

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
        table = Table("Ticket", "ID", "Jira", "Title", "State", "Priority", "Assigned To", "Pts")
        for t in tasks:
            key = proj_keys.get(t["project_id"], "")
            num = t["number"] or ""
            ticket = f"{key}-{num}" if key and num else t["id"][:8]
            pts = str(t["story_points"]) if t["story_points"] else "-"
            jira_key = t.get("jira_issue_key") or "-"
            table.add_row(ticket, t["id"][:8], jira_key, t["title"], t["state"],
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
        jira_key = task.get("jira_issue_key") or "-"
        body = (
            f"[bold]{task['title']}[/]\n"
            f"Jira: [cyan]{jira_key}[/]  "
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
        if ctx.get("worklogs"):
            console.print("\n[bold]Worklogs:[/]")
            for w in ctx["worklogs"]:
                sync_status = "[green]synced[/]" if w.get("synced_to_jira") else "[yellow]pending[/]"
                mins = w.get("time_spent_seconds", 0) // 60
                console.print(f"  [{w['tool']}] {w['agent_name']}: {w['summary'][:60]} ({mins}m) {sync_status}")
        if ctx["comments"]:
            console.print("\n[bold]Comments:[/]")
            for c in ctx["comments"]:
                console.print(f"  [{c['author_type']}] {c['author']}: {c['body']}")
    asyncio.run(_run())

@app.command("heartbeat")
def heartbeat_task(
    task_id: str = typer.Argument(...),
    progress: str = typer.Argument(..., help="Short progress note, e.g. 'wired up the parser, tests next'"),
    by: str = typer.Option("human", "--by", "-b", help="Agent name"),
):
    """Post a lightweight progress heartbeat. Other agents picking up the task
    see the latest one in `slate task context`."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await add_comment(db, task_id=task_id, author=by,
                              body=progress, author_type="agent", kind="heartbeat")
            console.print(f"[green]Heartbeat[/] logged for {task_id[:8]}")
    asyncio.run(_run())

@app.command("context")
def context_task(
    task_id: str = typer.Argument(...),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON for agent consumption"),
):
    """The brief an agent should read before starting: state, decisions, latest
    progress, and recent worklogs/comments — the shared memory for this task."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            ctx = await get_task_context(db, task_id)
        task = ctx["task"]
        if not task:
            console.print("[red]Task not found[/]")
            raise typer.Exit(1)
        if as_json:
            console.print_json(json.dumps(ctx, default=str))
            return
        jira_key = task.get("jira_issue_key") or "-"
        header = (
            f"[bold]{task['title']}[/]\n"
            f"Jira: [cyan]{jira_key}[/]  State: [yellow]{task['state']}[/]  "
            f"Priority: {task['priority']}  Assignee: {task.get('assigned_to') or '-'}"
        )
        if task.get("description"):
            header += f"\n\n{task['description']}"
        console.print(Panel(header, title="Task Brief"))

        decisions = ctx.get("decisions") or []
        if decisions:
            console.print("\n[bold magenta]Decisions:[/]")
            for d in decisions:
                console.print(f"  • {d['body']}  [dim](— {d['author']})[/]")

        hb = ctx.get("latest_heartbeat")
        if hb:
            console.print(f"\n[bold]Latest progress:[/] {hb['body']}  [dim](— {hb['author']})[/]")

        worklogs = ctx.get("worklogs") or []
        if worklogs:
            console.print("\n[bold]Recent work:[/]")
            for w in worklogs[-8:]:
                mins = w.get("time_spent_seconds", 0) // 60
                console.print(f"  • {w['summary'][:90]} ({mins}m)")

        notes = ctx.get("notes") or []
        if notes:
            console.print("\n[bold]Notes:[/]")
            for c in notes[-8:]:
                console.print(f"  • {c['body'][:100]}  [dim](— {c['author']})[/]")
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
