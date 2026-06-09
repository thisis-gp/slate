from __future__ import annotations
import asyncio
import typer
from rich.console import Console
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import get_task_context
from slate.obsidian.vault import (
    resolve_vault_path, write_issue_doc, read_issue_doc, issue_doc_path,
)

app = typer.Typer(help="Obsidian vault sync (one markdown doc per Jira issue)")
console = Console(legacy_windows=False)


def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@app.command("path")
def path_cmd():
    """Show the resolved vault path (project override or SLATE_VAULT_PATH)."""
    vp = resolve_vault_path()
    if not vp:
        console.print("[yellow]No vault configured.[/] Set SLATE_VAULT_PATH or "
                      ".agents/slate.json {\"vault_path\": \"...\"}")
        raise typer.Exit(1)
    console.print(f"[green]Vault:[/] {vp}")


@app.command("sync")
def sync_cmd(
    task_id: str = typer.Argument(..., help="Slate task ID or ticket"),
    subfolder: str = typer.Option("slate", "--subfolder", "-s", help="Per-repo subfolder"),
):
    """Write/update the Obsidian doc for a task's linked Jira issue."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            ctx = await get_task_context(db, task_id)
        task = ctx.get("task")
        if not task:
            console.print(f"[red]Task {task_id} not found[/]")
            raise typer.Exit(1)
        jira_key = task.get("jira_issue_key")
        if not jira_key:
            console.print("[yellow]Task has no Jira key — nothing to sync.[/]")
            raise typer.Exit(1)
        path = write_issue_doc(jira_key, ctx, title=task.get("title"), subfolder=subfolder)
        if not path:
            console.print("[yellow]No vault configured.[/] Run: slate obsidian path")
            raise typer.Exit(1)
        console.print(f"[green]Wrote[/] {path}")
    asyncio.run(_run())


@app.command("show")
def show_cmd(jira_key: str = typer.Argument(...),
            subfolder: str = typer.Option("slate", "--subfolder", "-s")):
    """Print the current Obsidian doc for a Jira key."""
    text = read_issue_doc(jira_key, subfolder)
    if text is None:
        p = issue_doc_path(jira_key, subfolder)
        console.print(f"[yellow]No doc at[/] {p or '(no vault configured)'}")
        raise typer.Exit(1)
    console.print(text)
