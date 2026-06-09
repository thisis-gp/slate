from __future__ import annotations
import typer
from slate.cli.projects import app as projects_app
from slate.cli.tasks import app as tasks_app
from slate.cli.runs import app as runs_app
from slate.cli.sessions import app as sessions_app
from slate.cli.comments import app as comments_app
from slate.cli.sync import app as sync_app
from slate.cli.sprints import app as sprints_app
from slate.cli.jira import app as jira_app
from slate.cli.worklog import app as worklog_app
from slate.cli.notify import app as notify_app
from slate.cli.obsidian import app as obsidian_app

app = typer.Typer(name="slate", help="Slate - Agentic Jira CLI", no_args_is_help=True)
app.add_typer(projects_app, name="project")
app.add_typer(tasks_app, name="task")
app.add_typer(runs_app, name="run")
app.add_typer(sessions_app, name="session")
app.add_typer(comments_app, name="comment")
app.add_typer(sync_app, name="sync")
app.add_typer(sprints_app, name="sprint")
app.add_typer(jira_app, name="jira")
app.add_typer(worklog_app, name="worklog")
app.add_typer(notify_app, name="notify")
app.add_typer(obsidian_app, name="obsidian")

if __name__ == "__main__":
    app()
