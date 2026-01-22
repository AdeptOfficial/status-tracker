"""Test fixtures for status-tracker tests."""

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base


@pytest_asyncio.fixture
async def db_session():
    """
    In-memory SQLite async database for tests.

    Creates a fresh database for each test, with all tables.
    Uses StaticPool to keep the same connection across the session
    (required for in-memory SQLite with async).
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.fixture
def load_webhook():
    """
    Load captured webhook JSON by name.

    Usage:
        payload = load_webhook("radarr-grab")
        payload = load_webhook("jellyseerr-movie-auto-approved")
    """
    def _load(name: str) -> dict:
        # Support both with and without .json extension
        if not name.endswith(".json"):
            name = f"{name}.json"

        path = Path(__file__).parent / "fixtures" / "webhooks" / name
        if not path.exists():
            raise FileNotFoundError(f"Webhook fixture not found: {path}")

        return json.loads(path.read_text())

    return _load


@pytest.fixture
def webhook_dir() -> Path:
    """Return path to captured webhooks directory."""
    return Path(__file__).parent / "fixtures" / "webhooks"
