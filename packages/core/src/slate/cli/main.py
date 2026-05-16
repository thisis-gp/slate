from __future__ import annotations
import typer
from slate.cli.projects import app as projects_app
from slate.cli.tasks import app as tasks_app
from slate.cli.runs import app as runs_app
from slate.cli.sessions import app as sessions_app
from slate.cli.approvals import app as approvals_app
from slate.cli.sync import app as sync_app

app = typer.Typer(name="slate", help="Slate - Agentic Jira CLI", no_args_is_help=True)
app.add_typer(projects_app, name="project")
app.add_typer(tasks_app, name="task")
app.add_typer(runs_app, name="run")
app.add_typer(sessions_app, name="session")
app.add_typer(approvals_app, name="approve")
app.add_typer(sync_app, name="sync")

if __name__ == "__main__":
    app()
