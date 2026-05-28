from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slate.db.schema import apply_schema
from slate.api.routes.health import router as health_router
from slate.api.routes.projects import router as projects_router
from slate.api.routes.tasks import router as tasks_router
from slate.api.routes.runs import router as runs_router
from slate.api.routes.sessions import router as sessions_router
from slate.api.routes.sync import router as sync_router
from slate.api.routes.sprints import router as sprints_router
from slate.api.routes.jira import router as jira_router
from slate.db.queries import get_jira_config
from slate.jira.scheduler import run_scheduler

DB_PATH = Path.home() / ".slate" / "db.sqlite"


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not hasattr(app.state, "db") or app.state.db is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(DB_PATH)
            conn.row_factory = aiosqlite.Row
            await apply_schema(conn)
            app.state.db = conn

        scheduler_task = None
        config = await get_jira_config(app.state.db)
        if config and config.get("enabled"):
            scheduler_task = asyncio.create_task(
                run_scheduler(config["sync_time"], DB_PATH)
            )

        yield

        if scheduler_task:
            scheduler_task.cancel()
        if hasattr(app.state, "db") and app.state.db:
            await app.state.db.close()

    app = FastAPI(title="Slate", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(tasks_router)
    app.include_router(runs_router)
    app.include_router(sessions_router)
    app.include_router(sync_router)
    app.include_router(sprints_router)
    app.include_router(jira_router)
    return app
