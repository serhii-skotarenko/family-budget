from sqlalchemy import text

from budget_bot.db import create_engine


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
