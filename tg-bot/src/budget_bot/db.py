"""Async engine and session factory."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets readers and writers proceed concurrently instead of
        # blocking each other; it persists in the database file itself, so
        # only the first connection actually switches the mode, but setting
        # it on every connect is harmless. (An in-memory test DB reports
        # "memory" here regardless — that's SQLite's own behavior, not a
        # sign this isn't wired up.)
        cursor.execute("PRAGMA journal_mode=WAL")
        # A concurrent writer no longer surfaces "database is locked"
        # immediately — it waits up to this long for the lock instead.
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
