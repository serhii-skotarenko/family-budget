"""Composition root: wires config, database, middlewares and handlers."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from budget_bot.bot.handlers import build_router
from budget_bot.bot.middlewares import AccessMiddleware, DbSessionMiddleware
from budget_bot.config import Settings
from budget_bot.db import create_engine, create_session_factory

BOT_COMMANDS = [
    BotCommand(command="add", description="Додати витрату"),
    BotCommand(command="list", description="Останні витрати"),
    BotCommand(command="filter", description="Фільтр витрат"),
    BotCommand(command="report", description="Звіт за період"),
    BotCommand(command="categories", description="Категорії"),
    BotCommand(command="cancel", description="Перервати діалог"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # MemoryStorage is enough for two users: a restart only drops in-flight
    # dialogs, never saved data.
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["settings"] = settings

    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    access = AccessMiddleware(settings.allowed_telegram_ids, settings.household_name)
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)

    dispatcher.include_router(build_router())

    await bot.set_my_commands(BOT_COMMANDS)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
