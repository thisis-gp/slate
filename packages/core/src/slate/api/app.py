from __future__ import annotations
import aiosqlite
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slate.db.schema import apply_schema
from slate.api.routes.health import router as health_router
from slate.api.routes.tasks import router as tasks_router


def create_app(db_path: str = "~/.slate/db.sqlite") -> FastAPI:
    resolved = os.path.expanduser(db_path)
    dir_part = os.path.dirname(resolved)
    if dir_part:
        os.makedirs(dir_part, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with aiosqlite.connect(resolved) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await apply_schema(conn)
            app.state.db = conn
            yield

    app = FastAPI(title="Agentic OS", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(tasks_router)
    return app
