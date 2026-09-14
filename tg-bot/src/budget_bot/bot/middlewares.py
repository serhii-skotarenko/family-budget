"""Outer middlewares: one DB session per update, whitelist enforcement."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from budget_bot.services.access import resolve_member

logger = logging.getLogger(__name__)

DENIED_TEXT = "⛔️ Доступ заборонено."
GROUP_CHAT_TEXT = "⛔️ Бот працює лише в особистих чатах."


class DbSessionMiddleware(BaseMiddleware):
    """Opens one session per update and commits it if the handler succeeded."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result


class AccessMiddleware(BaseMiddleware):
    """Rejects updates from Telegram IDs outside the whitelist, and any group chat.

    Runs on messages and callback queries only. ``event.from_user`` can
    still be ``None`` for some message types (e.g. a post automatically
    forwarded from a linked channel); ``_deny`` treats that the same as an
    unrecognized user.

    The MVP is scoped to two people talking to the bot directly (see
    docs/requirements.md). If a whitelisted member adds the bot to a group,
    a plain user check would still let them run e.g. /list there and dump
    the family's expense history into that chat, so non-private chats are
    rejected the same way an unknown user is.

    Every rejection is logged, so an unknown account probing the bot is
    visible in production logs. The record carries the Telegram user id, the
    chat type and the event kind — never the person's name or message text,
    which belong to someone who never agreed to be recorded.
    """

    def __init__(self, allowed_ids: frozenset[int], household_name: str) -> None:
        self.allowed_ids = allowed_ids
        self.household_name = household_name

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or user.id not in self.allowed_ids:
            logger.warning(
                "Access denied: Telegram user %s is not whitelisted (%s in a %s chat)",
                user.id if user is not None else None,
                type(event).__name__,
                self._chat_type(event),
            )
            await self._deny(event, DENIED_TEXT)
            return None

        if not self._is_private_chat(event):
            logger.warning(
                "Access denied: whitelisted user %s wrote from a %s chat (%s)",
                user.id,
                self._chat_type(event),
                type(event).__name__,
            )
            await self._deny(event, GROUP_CHAT_TEXT)
            return None

        data["member"] = await resolve_member(
            data["session"],
            telegram_id=user.id,
            display_name=user.first_name or str(user.id),
            household_name=self.household_name,
        )
        return await handler(event, data)

    @staticmethod
    def _chat_type(event: TelegramObject) -> str | None:
        """The chat type Telegram reports for the event, or None without a chat."""
        if isinstance(event, Message):
            return event.chat.type
        if isinstance(event, CallbackQuery) and event.message is not None:
            return event.message.chat.type
        return None

    @staticmethod
    def _is_private_chat(event: TelegramObject) -> bool:
        """True when the event's chat is a private 1:1 chat with the bot.

        A Message always carries its chat. A CallbackQuery's message can be
        None or an InaccessibleMessage, both of which still expose ``.chat``.
        Anything we can't identify a chat for is treated as non-private.
        """
        return AccessMiddleware._chat_type(event) == "private"

    @staticmethod
    async def _deny(event: TelegramObject, text: str) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
            return
        await event.answer(text)
