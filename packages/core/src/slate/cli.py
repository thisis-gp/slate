from __future__ import annotations
import typer
import uvicorn
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="slate",
    help="Agent orchestration framework — company hierarchy of AI workers.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Task prompt for the agent team"),
    config: str = typer.Option(".slate/config.yaml", help="Config file path"),
):
    """Submit a task to the agent orchestrator."""
    console.print(f"[bold green]Submitting task:[/] {prompt}")
    console.print("[yellow]Orchestrator coming in Phase 03...[/]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    port: int = typer.Option(7331, help="Port to bind"),
):
    """Start the Agentic OS API server."""
    from slate.api.app import create_app
    api_app = create_app()
    console.print(f"[bold green]Starting Agentic OS server[/] at http://{host}:{port}")
    uvicorn.run(api_app, host=host, port=port)


@app.command()
def status():
    """Show status of running tasks."""
    console.print("[yellow]Status view coming in Phase 03...[/]")


@app.command()
def cost():
    """Show today's API cost breakdown."""
    console.print("[yellow]Cost breakdown coming in Phase 02...[/]")


@app.command()
def init(
    path: str = typer.Option(".", help="Project path to initialize"),
):
    """Initialize .slate/config.yaml in the current project."""
    import shutil
    from pathlib import Path
    target = Path(path) / ".slate" / "config.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).parent.parent.parent.parent.parent / ".slate" / "config.yaml"
    if template.exists():
        shutil.copy(template, target)
        console.print(f"[green]Created[/] {target}")
    else:
        console.print(f"[red]Template not found.[/] Create {target} manually.")


if __name__ == "__main__":
    app()
