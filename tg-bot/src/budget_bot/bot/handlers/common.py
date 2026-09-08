"""/start, /help and the global /cancel escape hatch."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from budget_bot.bot.callbacks import FlowCb
from budget_bot.bot.keyboards import main_menu
from budget_bot.bot.replies import edit_or_answer
from budget_bot.models import Member

router = Router(name="common")

HELP_TEXT = (
    "Що я вмію:\n"
    "➕ /add — додати витрату\n"
    "📋 /list — останні витрати\n"
    "🔎 /filter — фільтр за періодом, категорією, автором\n"
    "📊 /report — звіт за тиждень / місяць / рік\n"
    "🏷 /categories — список категорій і додавання власної\n"
    "❌ /cancel — перервати поточний діалог\n\n"
    "Суми — у гривнях, цілими числами. Усі записи спільні для родини."
)


@router.message(CommandStart())
async def cmd_start(message: Message, member: Member) -> None:
    await message.answer(
        f"👋 Привіт, {escape(member.display_name)}! Це бот сімейного бюджету.\n\n{HELP_TEXT}",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    had_dialog = await state.get_state() is not None
    await state.clear()
    text = "❌ Скасовано." if had_dialog else "Немає активного діалогу."
    await message.answer(text, reply_markup=main_menu())


@router.callback_query(FlowCb.filter(F.action == "cancel"), StateFilter("*"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(callback, "❌ Скасовано.")
    await callback.answer()
