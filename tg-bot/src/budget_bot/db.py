"""Async engine and session factory."""

from pathlib import Path

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


def create_readonly_engine(database_path: Path) -> AsyncEngine:
    """Engine that can only read the bot's SQLite file (used by the Claude connector).

    Two independent guards: SQLite opens the file with ``mode=ro``, and every
    connection sets ``query_only``. No journal_mode pragma here — switching it
    is a write; the bot's engine has already put the file into WAL mode.
    """
    engine = create_async_engine(
        f"sqlite+aiosqlite:///file:{database_path}?mode=ro&uri=true",
        echo=False,
        # A failure's error text includes bound parameters (dates, amounts,
        # search text); never let that reach the logs.
        hide_parameters=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:
        # Let SQLAlchemy emit BEGIN itself (see _begin): the driver's own
        # transaction handling never starts one before a SELECT, so each
        # statement would otherwise read its own snapshot.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA query_only=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _begin(connection) -> None:
        # One snapshot per transaction, so one tool call's numbers agree.
        connection.exec_driver_sql("BEGIN")

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
