import contextlib

from sqlalchemy import func, select

from budget_bot.bot.middlewares import DENIED_TEXT, AccessMiddleware, DbSessionMiddleware
from budget_bot.db import create_engine, create_session_factory
from budget_bot.models import Base, Household
from tests.conftest import FakeCallback, FakeMessage


async def test_access_middleware_injects_member_and_calls_handler(session):
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")
    captured: dict = {}

    async def handler(event, data):
        captured.update(data)
        return "handled"

    result = await middleware(handler, FakeMessage(text="/start"), {"session": session})

    assert result == "handled"
    assert captured["member"].telegram_id == 111
    assert captured["member"].display_name == "Сергій"


async def test_access_middleware_blocks_unknown_telegram_id(session):
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")
    calls = []

    async def handler(event, data):
        calls.append(event)

    message = FakeMessage(text="/start", user_id=999)
    result = await middleware(handler, message, {"session": session})

    assert result is None
    assert calls == []
    assert message.last_reply == DENIED_TEXT
    assert await session.scalar(select(func.count()).select_from(Household)) == 0


async def test_access_middleware_blocks_unknown_user_on_callback(session):
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")

    async def handler(event, data):
        raise AssertionError("handler must not be called")

    callback = FakeCallback(user_id=999)
    await middleware(handler, callback, {"session": session})

    assert callback.answers[-1] == (DENIED_TEXT, True)


async def test_db_session_middleware_commits_on_success(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)

    async def handler(event, data):
        data["session"].add(Household(name="Сім'я"))

    await DbSessionMiddleware(factory)(handler, FakeMessage(), {})

    async with factory() as check:
        assert await check.scalar(select(func.count()).select_from(Household)) == 1
    await engine.dispose()


async def test_db_session_middleware_rolls_back_on_error(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)

    async def handler(event, data):
        data["session"].add(Household(name="Сім'я"))
        await data["session"].flush()
        raise RuntimeError("boom")

    with contextlib.suppress(RuntimeError):
        await DbSessionMiddleware(factory)(handler, FakeMessage(), {})

    async with factory() as check:
        assert await check.scalar(select(func.count()).select_from(Household)) == 0
    await engine.dispose()
