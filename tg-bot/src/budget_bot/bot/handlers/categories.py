"""/categories: show the shared list and add a custom category."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import FlowCb
from budget_bot.bot.keyboards import BTN_CATEGORIES, add_category_keyboard, cancel_keyboard
from budget_bot.models import Member
from budget_bot.services.categories import (
    CategoryNameError,
    DuplicateCategoryError,
    add_category,
    list_categories,
)

router = Router(name="categories")


class AddCategory(StatesGroup):
    name = State()


@router.message(Command("categories"))
@router.message(F.text == BTN_CATEGORIES)
async def cmd_categories(message: Message, session: AsyncSession, member: Member) -> None:
    categories = await list_categories(session, member.household_id)
    lines = ["<b>🏷 Категорії</b>", ""]
    lines.extend(
        f"• {escape(item.name)}" + (" (власна)" if item.is_custom else "") for item in categories
    )
    await message.answer("\n".join(lines), reply_markup=add_category_keyboard())


@router.callback_query(FlowCb.filter(F.action == "add_category"))
async def cb_start_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCategory.name)
    await callback.message.answer("Введіть назву нової категорії:", reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(AddCategory.name)
async def enter_category_name(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        category = await add_category(session, member.household_id, message.text or "")
    except (DuplicateCategoryError, CategoryNameError) as error:
        # Stay in the same state so the user can retype without restarting.
        # escape(): DuplicateCategoryError embeds another user's raw category
        # name, so this text is not safe to interpolate unescaped.
        await message.answer(f"⚠️ {escape(str(error))}", reply_markup=cancel_keyboard())
        return

    await state.clear()
    await message.answer(f"✅ Категорію «{escape(category.name)}» додано.")
