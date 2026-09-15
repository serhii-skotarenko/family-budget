import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from budget_bot.db import create_engine, create_readonly_engine


async def test_connect_pragmas_enable_wal_and_busy_timeout_on_a_real_file(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'pragmas.sqlite3'}")

    async with engine.connect() as connection:
        journal_mode = (await connection.execute(text("PRAGMA journal_mode"))).scalar()
        busy_timeout = (await connection.execute(text("PRAGMA busy_timeout"))).scalar()
        foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar()

    assert journal_mode == "wal"
    assert busy_timeout == 10000
    assert foreign_keys == 1

    await engine.dispose()


async def test_readonly_engine_rejects_writes_but_sees_the_bots_commits(tmp_path):
    path = tmp_path / "budget.sqlite3"
    writer = create_engine(f"sqlite+aiosqlite:///{path}")
    reader = create_readonly_engine(path)
    try:
        async with writer.begin() as connection:
            await connection.execute(text("CREATE TABLE t (x INTEGER)"))
            await connection.execute(text("INSERT INTO t VALUES (1)"))

        async with reader.connect() as connection:
            with pytest.raises(OperationalError, match="readonly database"):
                await connection.execute(text("INSERT INTO t VALUES (2)"))

        async with writer.begin() as connection:
            await connection.execute(text("INSERT INTO t VALUES (3)"))
        async with reader.connect() as connection:
            assert (await connection.execute(text("SELECT count(*) FROM t"))).scalar() == 2
    finally:
        await reader.dispose()
        await writer.dispose()


async def test_readonly_engine_reads_while_the_bot_holds_no_connection(tmp_path):
    path = tmp_path / "budget.sqlite3"
    writer = create_engine(f"sqlite+aiosqlite:///{path}")
    async with writer.begin() as connection:
        await connection.execute(text("CREATE TABLE t (x INTEGER)"))
        await connection.execute(text("INSERT INTO t VALUES (1)"))
    await writer.dispose()  # a clean close removes the WAL side files

    reader = create_readonly_engine(path)
    try:
        async with reader.connect() as connection:
            assert (await connection.execute(text("SELECT count(*) FROM t"))).scalar() == 1
    finally:
        await reader.dispose()
