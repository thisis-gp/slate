import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from httpx import AsyncClient, ASGITransport
from agentic_os.api.app import create_app


@pytest_asyncio.fixture
async def client(tmp_path):
    """Test client with proper lifespan management for FastAPI app."""
    app = create_app(db_path=str(tmp_path / "test.sqlite"))

    # Get the lifespan context manager from the app
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
