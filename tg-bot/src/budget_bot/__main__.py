"""Composition root: wires config, database, middlewares, handlers and the Claude connector."""

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, Update

from budget_bot.bot.handlers import build_router
from budget_bot.bot.middlewares import AccessMiddleware, DbSessionMiddleware
from budget_bot.config import Settings
from budget_bot.connector.server import (
    build_connector_app,
    build_connector_server,
    connector_config,
    serve_connector,
)
from budget_bot.db import create_engine, create_readonly_engine, create_session_factory

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="add", description="Додати витрату"),
    BotCommand(command="list", description="Останні витрати"),
    BotCommand(command="filter", description="Фільтр витрат"),
    BotCommand(command="report", description="Звіт за період"),
    BotCommand(command="limits", description="Ліміти та прогрес"),
    BotCommand(command="setlimit", description="Встановити ліміт"),
    BotCommand(command="setincome", description="Місячний дохід"),
    BotCommand(command="categories", description="Категорії"),
    BotCommand(command="cancel", description="Перервати діалог"),
]

APOLOGY_TEXT = "⚠️ Виникла помилка. Спробуйте ще раз або /cancel."


def _chat_id(update: Update) -> int | None:
    if update.message is not None:
        return update.message.chat.id
    if update.callback_query is not None and update.callback_query.message is not None:
        return update.callback_query.message.chat.id
    return None


async def handle_error(event: ErrorEvent, bot: Bot) -> None:
    """Last-resort catch for exceptions no router or middleware handled.

    Registered on ``dispatcher.errors`` so an unhandled exception no longer
    just logs a traceback and leaves the user without a reply. Must never
    itself raise — that would propagate out of aiogram's ErrorsMiddleware
    and abort update processing.
    """
    logger.exception(
        "Unhandled error while processing update %s",
        event.update.update_id,
        exc_info=event.exception,
    )
    chat_id = _chat_id(event.update)
    if chat_id is None:
        return
    try:
        await bot.send_message(chat_id, APOLOGY_TEXT)
    except Exception:  # noqa: BLE001 - notifying about the error must not itself raise
        logger.exception("Failed to notify chat %s about an error", chat_id)


async def run_bot(dispatcher: Dispatcher, bot: Bot, connector: uvicorn.Server | None) -> None:
    """Poll Telegram until SIGINT/SIGTERM, running the Claude connector alongside.

    aiogram owns the signals. The connector starts first and is stopped only
    after polling has ended; its own failure never ends polling (see
    serve_connector).
    """
    connector_task = (
        asyncio.create_task(serve_connector(connector)) if connector is not None else None
    )
    try:
        await bot.set_my_commands(BOT_COMMANDS)
        await dispatcher.start_polling(bot)
    finally:
        if connector is not None and connector_task is not None:
            connector.should_exit = True
            await connector_task


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
    dispatcher.errors.register(handle_error)

    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    access = AccessMiddleware(settings.allowed_telegram_ids, settings.household_name)
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)

    dispatcher.include_router(build_router())

    readonly_engine = None
    connector = None
    config = connector_config(settings)
    if config is not None:
        readonly_engine = create_readonly_engine(settings.database_path)
        app = build_connector_app(
            create_session_factory(readonly_engine), config.tokens, config.public_host
        )
        connector = build_connector_server(app, config.port)

    try:
        await run_bot(dispatcher, bot, connector)
    finally:
        await bot.session.close()
        if readonly_engine is not None:
            await readonly_engine.dispose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
