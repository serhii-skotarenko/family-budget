"""Shared reply helper for callback-query handlers."""

from typing import Any

from aiogram.types import CallbackQuery, Message


async def edit_or_answer(callback: CallbackQuery, text: str, **kwargs: Any) -> None:
    """Edit the callback's message in place, or send a fresh reply when it can't be edited.

    ``CallbackQuery.message`` is typed as ``Message | InaccessibleMessage | None``.
    Telegram substitutes ``InaccessibleMessage`` once a message is more than 48 hours
    old, and that type defines ``answer()`` but not ``edit_text()``. Calling
    ``edit_text`` unconditionally would raise ``AttributeError`` in that case —
    dangerous when it happens after a write has already been committed (see
    ``add_expense.save_expense``). Route every such call through here instead.
    """
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(text, **kwargs)
    elif message is not None:
        await message.answer(text, **kwargs)
