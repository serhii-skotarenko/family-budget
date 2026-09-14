import contextlib
import logging

import pytest
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


async def test_access_middleware_blocks_group_chat_message(session):
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")
    calls = []

    async def handler(event, data):
        calls.append(event)

    message = FakeMessage(text="/start", chat_type="group")
    result = await middleware(handler, message, {"session": session})

    assert result is None
    assert calls == []
    assert "особист" in message.last_reply.lower()
    assert await session.scalar(select(func.count()).select_from(Household)) == 0


async def test_access_middleware_blocks_group_chat_callback(session):
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")

    async def handler(event, data):
        raise AssertionError("handler must not be called")

    callback = FakeCallback(chat_type="group")
    await middleware(handler, callback, {"session": session})

    assert callback.answers[-1][1] is True
    assert "особист" in callback.answers[-1][0].lower()


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


MIDDLEWARE_LOGGER = "budget_bot.bot.middlewares"


def _middleware_records(caplog):
    return [record for record in caplog.records if record.name == MIDDLEWARE_LOGGER]


@pytest.mark.parametrize(
    "make_event",
    [
        lambda: FakeMessage(text="мій секретний пароль 12345", user_id=999, first_name="Stranger"),
        lambda: FakeCallback(user_id=999, first_name="Stranger"),
    ],
    ids=["message", "callback"],
)
async def test_denied_stranger_is_logged_without_their_text_or_name(session, caplog, make_event):
    # Breaks if: the denial goes unlogged (strangers invisible again), is logged
    # below the production level, names the wrong user, or copies the
    # stranger's message text or name into the logs.
    caplog.set_level(logging.DEBUG, logger=MIDDLEWARE_LOGGER)
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")

    async def handler(event, data):
        raise AssertionError("handler must not be called")

    await middleware(handler, make_event(), {"session": session})

    records = _middleware_records(caplog)
    assert len(records) == 1
    assert records[0].levelno >= logging.INFO
    text = records[0].getMessage()
    assert "999" in text
    assert "секретний пароль" not in text
    assert "Stranger" not in text


async def test_group_chat_denial_is_logged_with_member_and_chat_type(session, caplog):
    # Breaks if: a group-chat rejection leaves no trace, or its record carries
    # neither the member's id nor the chat type.
    caplog.set_level(logging.DEBUG, logger=MIDDLEWARE_LOGGER)
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")

    async def handler(event, data):
        raise AssertionError("handler must not be called")

    await middleware(handler, FakeMessage(text="/list", chat_type="group"), {"session": session})

    records = _middleware_records(caplog)
    assert len(records) == 1
    assert records[0].levelno >= logging.INFO
    text = records[0].getMessage()
    assert "111" in text
    assert "group" in text


async def test_allowed_private_access_is_not_logged_as_a_denial(session, caplog):
    # Breaks if: the denial log call escapes its guard and fires on every
    # update, burying real denials under the family's normal traffic.
    caplog.set_level(logging.DEBUG, logger=MIDDLEWARE_LOGGER)
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")

    async def handler(event, data):
        return "handled"

    await middleware(handler, FakeMessage(text="/start"), {"session": session})

    assert _middleware_records(caplog) == []
