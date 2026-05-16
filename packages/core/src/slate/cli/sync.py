from __future__ import annotations
import asyncio
from datetime import date, timedelta
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import get_daily_sync

app = typer.Typer(help="Generate sync reports")
console = Console(legacy_windows=False)

def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _render_daily(data: dict) -> None:
    d = data["date"]
    runs = data["runs"]
    transitions = data["transitions"]
    sessions = data["sessions"]
    cost = data["total_cost_usd"]

    # Header stats
    console.print(Panel(
        f"Sessions: [bold]{len(sessions)}[/]   "
        f"Agent Runs: [bold]{len(runs)}[/]   "
        f"State Changes: [bold]{len(transitions)}[/]   "
        f"Total Cost: [yellow bold]${cost:.4f}[/]",
        title=f"Daily Sync - {d}",
    ))

    # Tasks touched (unique set from both runs and transitions)
    task_titles: dict[str, str] = {}
    for r in runs:
        task_titles[r["task_id"]] = r.get("task_title") or r["task_id"][:8]
    for t in transitions:
        task_titles[t["task_id"]] = t.get("task_title") or t["task_id"][:8]

    if not task_titles:
        console.print("[dim]No task activity today.[/]")
        return

    console.print(f"\n[bold]Tasks touched today ({len(task_titles)}):[/]")

    for tid, title in task_titles.items():
        task_runs = [r for r in runs if r["task_id"] == tid]
        task_transitions = [t for t in transitions if t["task_id"] == tid]
        task_cost = sum(r.get("cost_usd", 0) for r in task_runs)

        header = Text()
        header.append(f"  {title}", style="bold white")
        if task_cost > 0:
            header.append(f"  ${task_cost:.4f}", style="yellow")
        console.print(header)

        for t in task_transitions:
            frm = t.get("from_state") or "-"
            console.print(f"    [dim]state:[/] {frm} -> [cyan]{t['to_state']}[/] [dim]by {t['changed_by']}[/]"
                         + (f"  [dim italic]{t['reason']}[/]" if t.get("reason") else ""))

        for r in task_runs:
            run_cost = f"  [yellow]${r.get('cost_usd', 0):.4f}[/]" if r.get("cost_usd") else ""
            tool = r['tool'].encode('ascii', 'replace').decode()
            summary = r['summary'][:80].encode('ascii', 'replace').decode()
            console.print(f"    [dim]run:[/]   [blue]\\[{tool}][/] {r['agent_name']}: {summary}{run_cost}")

@app.command("daily")
def daily(target_date: str = typer.Option("", "--date", "-d")):
    d = target_date or date.today().isoformat()
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            data = await get_daily_sync(db, d)
        _render_daily(data)
    asyncio.run(_run())

@app.command("weekly")
def weekly():
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            today = date.today()
            days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
            all_data = [await get_daily_sync(db, d) for d in days]

        total_runs = sum(len(d["runs"]) for d in all_data)
        total_cost = sum(d["total_cost_usd"] for d in all_data)
        active_days = [d for d in all_data if d["transitions"] or d["runs"]]

        console.print(Panel(
            f"Period: [bold]{days[0]} to {days[-1]}[/]\n"
            f"Active Days: [bold]{len(active_days)}[/]   "
            f"Total Runs: [bold]{total_runs}[/]   "
            f"Total Cost: [yellow bold]${total_cost:.4f}[/]",
            title="Weekly Sync",
        ))

        if not active_days:
            console.print("[dim]No activity this week.[/]")
            return

        for data in active_days:
            console.print(f"\n[bold cyan]{data['date']}[/]  "
                         f"[dim]{len(data['runs'])} runs  "
                         f"{len(data['transitions'])} transitions  "
                         f"${data['total_cost_usd']:.4f}[/]")
            task_titles: dict[str, str] = {}
            for r in data["runs"]:
                task_titles[r["task_id"]] = r.get("task_title") or r["task_id"][:8]
            for t in data["transitions"]:
                task_titles[t["task_id"]] = t.get("task_title") or t["task_id"][:8]
            for tid, title in task_titles.items():
                t_transitions = [t for t in data["transitions"] if t["task_id"] == tid]
                t_runs = [r for r in data["runs"] if r["task_id"] == tid]
                final_state = t_transitions[-1]["to_state"] if t_transitions else "-"
                run_cost = sum(r.get("cost_usd", 0) for r in t_runs)
                cost_str = f"  [yellow]${run_cost:.4f}[/]" if run_cost > 0 else ""
                safe_title = title.encode('ascii', 'replace').decode()
                console.print(f"  [white]{safe_title}[/]  ->  [cyan]{final_state}[/]{cost_str}")
    asyncio.run(_run())
