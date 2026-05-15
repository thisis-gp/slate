import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from slate.api.app import create_app
from slate.db.schema import apply_schema

@pytest.fixture
async def client():
    app = create_app()
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        await apply_schema(db)
        app.state.db = db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
