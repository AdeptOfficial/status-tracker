"""SQLite database setup with SQLAlchemy async."""

import logging
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# Convert sqlite:// to sqlite+aiosqlite:// for async
# Note: sqlite:/// = relative path, sqlite://// = absolute path
# We replace just "sqlite://" to preserve the path slashes
database_url = settings.DATABASE_URL
if database_url.startswith("sqlite://"):
    database_url = database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

engine = create_async_engine(
    database_url,
    echo=False,  # Set True for SQL debugging
    future=True,
    # SQLite concurrency settings to prevent "database is locked" errors
    connect_args={"check_same_thread": False, "timeout": 30},
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Alias for use with context manager (async with async_session() as db:)
async_session = async_session_maker


async def get_db() -> AsyncSession:
    """Dependency for FastAPI routes to get a database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def run_migrations(conn):
    """
    Run schema migrations to add missing columns.

    SQLAlchemy's create_all() only creates new tables, not new columns.
    This function checks each table for missing columns and adds them.

    Why not Alembic? For a homelab project, this simpler approach avoids
    the complexity of managing migration files. Trade-off: can only ADD
    columns, not modify or remove them.
    """
    # Get the inspector to check existing schema
    def get_existing_columns(connection):
        inspector = inspect(connection)
        existing = {}
        for table_name in inspector.get_table_names():
            existing[table_name] = {col['name'] for col in inspector.get_columns(table_name)}
        return existing

    existing_schema = await conn.run_sync(get_existing_columns)

    # Define migrations: table -> column -> (type, default)
    # Add new columns here when the model changes
    # NOTE: SQLAlchemy Enum stores the enum NAME (uppercase), not the value
    migrations = {
        "deletion_logs": {
            "status": ("VARCHAR(20)", "'IN_PROGRESS'"),
            "is_anime": ("BOOLEAN", "0"),  # For Shoko sync determination
        },
        "requests": {
            "alternate_titles": ("TEXT", "NULL"),  # JSON array of alternate titles for Shoko matching
        },
    }

    for table_name, columns in migrations.items():
        if table_name not in existing_schema:
            # Table doesn't exist yet, create_all will handle it
            continue

        for column_name, (column_type, default) in columns.items():
            if column_name not in existing_schema[table_name]:
                # Column is missing, add it
                default_clause = f"DEFAULT {default}" if default else ""
                sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} {default_clause}"
                logger.info(f"Migration: Adding column {table_name}.{column_name}")
                await conn.execute(text(sql))


async def init_db():
    """
    Initialize database on startup.

    1. Enable WAL mode for better concurrency
    2. Create any new tables (create_all)
    3. Run migrations to add missing columns to existing tables
    """
    async with engine.begin() as conn:
        # Enable WAL mode for concurrent reads during writes
        # This prevents "database is locked" errors from async operations
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=5000"))

        # Create any new tables
        await conn.run_sync(Base.metadata.create_all)

        # Run migrations for missing columns
        await run_migrations(conn)

    logger.info("Database initialized with WAL mode")
