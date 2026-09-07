"""Outer middlewares: one DB session per update, whitelist enforcement."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from budget_bot.services.access import resolve_member

DENIED_TEXT = "⛔️ Доступ заборонено."


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
    """Rejects updates from Telegram IDs outside the whitelist.

    Runs on messages and callback queries only. ``event.from_user`` can
    still be ``None`` for some message types (e.g. a post automatically
    forwarded from a linked channel); ``_deny`` treats that the same as an
    unrecognized user.
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
            await self._deny(event)
            return None

        data["member"] = await resolve_member(
            data["session"],
            telegram_id=user.id,
            display_name=user.first_name or str(user.id),
            household_name=self.household_name,
        )
        return await handler(event, data)

    @staticmethod
    async def _deny(event: TelegramObject) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(DENIED_TEXT, show_alert=True)
            return
        await event.answer(DENIED_TEXT)
