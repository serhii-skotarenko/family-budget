"""The bot's run loop with the real aiogram Dispatcher and a real connector server.

Only Telegram is faked. Started as a subprocess by test_connector_lifecycle.py:
``python connector_lifecycle_app.py <port>``.
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, GetUpdates, SetMyCommands
from aiogram.types import User
from starlette.applications import Starlette

from budget_bot.__main__ import run_bot
from budget_bot.connector.server import build_connector_server


class FakeTelegramSession(BaseSession):
    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="Test", username="test_bot")
        if isinstance(method, GetUpdates):
            await asyncio.sleep(0.1)
            return []
        if isinstance(method, SetMyCommands):
            # Like the real network call, this lets the connector start (and take
            # over signal handling, were it stock uvicorn) before aiogram
            # registers its own handlers.
            await asyncio.sleep(0.3)
            return True
        raise AssertionError(f"unexpected Telegram call: {type(method).__name__}")

    async def stream_content(self, *args, **kwargs):
        raise AssertionError("unexpected Telegram download")
        yield b""  # makes this an async generator, as the interface requires


async def main(port: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s", stream=sys.stdout)
    bot = Bot(token="42:TEST", session=FakeTelegramSession())
    connector = build_connector_server(Starlette(), port=port, host="127.0.0.1")
    try:
        await run_bot(Dispatcher(), bot, connector)
    finally:
        print("CLEANUP started", flush=True)
        await asyncio.sleep(1.0)  # stands in for closing the bot session and the engines
        print("CLEANUP finished", flush=True)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
