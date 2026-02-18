"""
Database setup — async SQLAlchemy with SQLite (dev) or Postgres (prod).

get_db() is the FastAPI dependency that gives you a session per request.
create_tables() creates new tables on startup.
run_migrations() adds columns to existing tables that SQLAlchemy's
create_all() won't handle (it only creates missing tables, not columns).
"""
import logging

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

from src.app.config import DATABASE_URL


# Create the async engine. check_same_thread=False needed for SQLite.
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, connect_args=connect_args)

# Session factory — each call produces a new async session
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db():
    """FastAPI dependency — yields a database session, auto-closes when done."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    """Create all tables. Called on app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _get_existing_columns(conn, table_name):
    """Get the set of column names for an existing table."""
    insp = inspect(conn)
    if not insp.has_table(table_name):
        return set()
    return {col["name"] for col in insp.get_columns(table_name)}


async def run_migrations():
    """
    Add columns to existing tables that create_all() won't handle.

    SQLAlchemy's create_all() only creates tables that don't exist — it won't
    add new columns to tables that already exist. This function checks for
    missing columns and adds them with ALTER TABLE.

    Each migration is idempotent — safe to run multiple times. If the column
    already exists, it's skipped.
    """
    # List of (table_name, column_name, column_sql) to ensure exist.
    # column_sql is the SQL type + constraints for the ALTER TABLE statement.
    migrations = [
        ("agents", "webhook_url", "VARCHAR(500) NULL"),
        ("connections", "contract_type", "VARCHAR(50) DEFAULT 'friends'"),
        # Phase 1: Email verification fields on users
        ("users", "verified", "BOOLEAN DEFAULT FALSE"),
        ("users", "verification_code", "VARCHAR(6) NULL"),
        ("users", "verification_expires_at", "TIMESTAMP NULL"),
        # Phase 2: Multi-agent — primary flag on agents
        ("agents", "is_primary", "BOOLEAN DEFAULT TRUE"),
        # Phase 3: Human-level connections — new user-level FK columns
        # Old agent-level columns stay in DB (SQLite can't drop them) but are unused
        ("connections", "user_a_id", "VARCHAR(16) REFERENCES users(id)"),
        ("connections", "user_b_id", "VARCHAR(16) REFERENCES users(id)"),
        ("invites", "from_user_id", "VARCHAR(16) REFERENCES users(id)"),
        ("invites", "used_by_user_id", "VARCHAR(16) REFERENCES users(id)"),
        ("permissions", "user_id", "VARCHAR(16) REFERENCES users(id)"),
        # Phase 4: Discover profile fields on users
        ("users", "bio", "TEXT NULL"),
        ("users", "interests", "TEXT NULL"),
        ("users", "looking_for", "TEXT NULL"),
        ("users", "discoverable", "BOOLEAN DEFAULT FALSE"),
        # Phase 5: Bento profile fields for Surge
        ("users", "superpower", "TEXT NULL"),
        ("users", "current_project", "TEXT NULL"),
        ("users", "need_help_with", "TEXT NULL"),
        ("users", "dream_collab", "TEXT NULL"),
        ("users", "fun_fact", "TEXT NULL"),
        ("users", "education", "TEXT NULL"),
        ("users", "photo_url", "TEXT NULL"),
    ]

    async with engine.begin() as conn:
        for table_name, column_name, column_sql in migrations:
            # Check if column already exists (run synchronously via run_sync)
            existing = await conn.run_sync(
                lambda sync_conn: _get_existing_columns(sync_conn, table_name)
            )

            if column_name not in existing:
                stmt = f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}'
                await conn.execute(text(stmt))
                logger.info(f"Migration: added {table_name}.{column_name}")
            else:
                logger.debug(f"Migration: {table_name}.{column_name} already exists, skipping")
