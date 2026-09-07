"""Catch-all handlers for updates nothing else claimed.

Included last in build_router() so it only fires after every feature router
has had a chance to match: a stale inline keyboard left over from a dropped
dialog (MemoryStorage loses in-flight FSM state on restart), plain text
typed while a keyboard-only state is active (there is no message handler
for e.g. AddExpense.category), or free text typed with no active dialog at
all. Without this, an unmatched callback leaves the client spinning for
~30 seconds and an unmatched message gets no reply at all.
"""

from aiogram import Router
from aiogram.types import CallbackQuery, Message

router = Router(name="fallback")

STALE_BUTTON_TEXT = "Ця кнопка застаріла — почніть спочатку."
UNRECOGNIZED_TEXT = "Не зрозумів. Скористайтесь /add або кнопками меню."


@router.callback_query()
async def unmatched_callback(callback: CallbackQuery) -> None:
    await callback.answer(STALE_BUTTON_TEXT, show_alert=True)


@router.message()
async def unmatched_message(message: Message) -> None:
    await message.answer(UNRECOGNIZED_TEXT)
