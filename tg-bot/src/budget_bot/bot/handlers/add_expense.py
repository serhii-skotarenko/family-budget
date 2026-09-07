"""/add: amount → category → optional description → confirmation."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.amounts import AmountError, format_amount, parse_amount
from budget_bot.bot.callbacks import CategoryCb, FlowCb
from budget_bot.bot.keyboards import (
    BTN_ADD,
    cancel_keyboard,
    categories_keyboard,
    confirm_keyboard,
    description_keyboard,
)
from budget_bot.bot.texts import MAX_DESCRIPTION_LENGTH
from budget_bot.formatting import format_saved_expense
from budget_bot.models import Member
from budget_bot.services.categories import get_category, list_categories
from budget_bot.services.expenses import create_expense

router = Router(name="add_expense")


class AddExpense(StatesGroup):
    amount = State()
    category = State()
    description = State()
    confirm = State()


@router.message(Command("add"))
@router.message(F.text == BTN_ADD)
async def start_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddExpense.amount)
    await message.answer(
        "💸 Введіть суму витрати в гривнях (ціле число):", reply_markup=cancel_keyboard()
    )


@router.message(AddExpense.amount)
async def enter_amount(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        amount = parse_amount(message.text or "")
    except AmountError as error:
        await message.answer(f"⚠️ {escape(str(error))}", reply_markup=cancel_keyboard())
        return

    await state.update_data(amount=amount)
    await state.set_state(AddExpense.category)
    categories = await list_categories(session, member.household_id)
    await message.answer("Оберіть категорію:", reply_markup=categories_keyboard(categories))


@router.callback_query(AddExpense.category, CategoryCb.filter(F.action == "pick"))
async def pick_category(
    callback: CallbackQuery,
    callback_data: CategoryCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    category = await get_category(session, member.household_id, callback_data.category_id)
    if category is None:
        await callback.answer("Категорію не знайдено. Оберіть іншу.", show_alert=True)
        return

    await state.update_data(category_id=category.id, category_name=category.name)
    await state.set_state(AddExpense.description)
    await callback.message.answer(
        f"Категорія: <b>{escape(category.name)}</b>\n\nДодайте опис або пропустіть цей крок:",
        reply_markup=description_keyboard(),
    )
    await callback.answer()


@router.message(AddExpense.description)
async def enter_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()[:MAX_DESCRIPTION_LENGTH] or None
    await _ask_confirmation(message, state, description)


@router.callback_query(AddExpense.description, FlowCb.filter(F.action == "skip"))
async def skip_description(callback: CallbackQuery, state: FSMContext) -> None:
    await _ask_confirmation(callback.message, state, None)
    await callback.answer()


async def _ask_confirmation(message: Message, state: FSMContext, description: str | None) -> None:
    data = await state.update_data(description=description)
    await state.set_state(AddExpense.confirm)
    summary = (
        "Перевірте запис:\n"
        f"Сума: <b>{format_amount(data['amount'])}</b>\n"
        f"Категорія: {escape(data['category_name'])}\n"
        f"Опис: {escape(description) if description else '—'}"
    )
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.callback_query(AddExpense.confirm, FlowCb.filter(F.action == "save"))
async def save_expense(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    data = await state.get_data()
    expense = await create_expense(
        session,
        household_id=member.household_id,
        member_id=member.id,
        category_id=data["category_id"],
        amount=data["amount"],
        description=data.get("description"),
    )
    await state.clear()
    await callback.message.edit_text(format_saved_expense(expense))
    await callback.answer()
