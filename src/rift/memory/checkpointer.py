"""Postgres checkpointer setup for LangGraph (`AsyncPostgresSaver` + `AsyncConnectionPool`)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from rift.config import get_settings


def checkpointer_dsn(database_url: str | None = None) -> str:
    """Convert SQLAlchemy's `postgresql+asyncpg://...` URL into a `psycopg` `postgresql://...` DSN."""
    raw = database_url or get_settings().database_url
    if raw.startswith("postgresql+asyncpg://"):
        return raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql://", 1)
    return raw


@asynccontextmanager
async def open_checkpointer(
    database_url: str | None = None, *, max_size: int = 10
) -> AsyncIterator[AsyncPostgresSaver]:
    """Open an `AsyncPostgresSaver` backed by a pooled `psycopg` connection and run `.setup()`."""
    pool = AsyncConnectionPool(
        checkpointer_dsn(database_url),
        max_size=max_size,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,  # safe behind PgBouncer / Neon pooled connections
            "row_factory": dict_row,
        },
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()  # idempotent: creates checkpoint tables on first run
        yield saver
    finally:
        await pool.close()
