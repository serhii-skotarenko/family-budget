"""Composition root: wires config, database, middlewares and handlers."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, Update

from budget_bot.bot.handlers import build_router
from budget_bot.bot.middlewares import AccessMiddleware, DbSessionMiddleware
from budget_bot.config import Settings
from budget_bot.db import create_engine, create_session_factory

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="add", description="Додати витрату"),
    BotCommand(command="list", description="Останні витрати"),
    BotCommand(command="filter", description="Фільтр витрат"),
    BotCommand(command="report", description="Звіт за період"),
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

    await bot.set_my_commands(BOT_COMMANDS)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
