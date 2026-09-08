"""Editing an existing expense. Any member may edit any record."""

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.amounts import AmountError, parse_amount
from budget_bot.bot.callbacks import CategoryCb, EditFieldCb, ExpenseCb
from budget_bot.bot.keyboards import cancel_keyboard, categories_keyboard, edit_fields_keyboard
from budget_bot.bot.predicates import NOT_A_COMMAND
from budget_bot.bot.texts import (
    CLEAR_DESCRIPTION_TOKEN,
    MAX_DESCRIPTION_LENGTH,
    MISSING_EXPENSE_TEXT,
)
from budget_bot.formatting import format_expense_card
from budget_bot.models import Member
from budget_bot.services.categories import get_category, list_categories
from budget_bot.services.expenses import get_expense, update_expense

router = Router(name="expense_edit")


class EditExpense(StatesGroup):
    amount = State()
    description = State()
    category = State()


@router.callback_query(ExpenseCb.filter(F.action == "edit"))
async def cb_edit_menu(
    callback: CallbackQuery,
    callback_data: ExpenseCb,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await callback.message.answer("Що змінюємо?", reply_markup=edit_fields_keyboard(expense.id))
    await callback.answer()


@router.callback_query(EditFieldCb.filter())
async def cb_pick_field(
    callback: CallbackQuery,
    callback_data: EditFieldCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await state.update_data(expense_id=expense.id)

    if callback_data.field == "amount":
        await state.set_state(EditExpense.amount)
        await callback.message.answer("Введіть нову суму:", reply_markup=cancel_keyboard())
    elif callback_data.field == "description":
        await state.set_state(EditExpense.description)
        await callback.message.answer(
            f"Введіть новий опис (або «{CLEAR_DESCRIPTION_TOKEN}», щоб прибрати):",
            reply_markup=cancel_keyboard(),
        )
    else:
        await state.set_state(EditExpense.category)
        categories = await list_categories(session, member.household_id)
        await callback.message.answer(
            "Оберіть нову категорію:",
            reply_markup=categories_keyboard(categories, action="edit"),
        )
    await callback.answer()


@router.message(EditExpense.amount, NOT_A_COMMAND)
async def enter_new_amount(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        amount = parse_amount(message.text or "")
    except AmountError as error:
        await message.answer(f"⚠️ {escape(str(error))}", reply_markup=cancel_keyboard())
        return

    await _apply(message, state, session, member, amount=amount)


@router.message(EditExpense.description, NOT_A_COMMAND)
async def enter_new_description(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    raw = (message.text or "").strip()
    description = None if raw == CLEAR_DESCRIPTION_TOKEN else raw[:MAX_DESCRIPTION_LENGTH] or None
    await _apply(message, state, session, member, description=description)


@router.callback_query(EditExpense.category, CategoryCb.filter(F.action == "edit"))
async def pick_new_category(
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

    await _apply(callback.message, state, session, member, category_id=category.id)
    await callback.answer()


async def _apply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
    **changes,
) -> None:
    data = await state.get_data()
    expense = await get_expense(session, member.household_id, data["expense_id"])
    if expense is None:
        await state.clear()
        await message.answer(MISSING_EXPENSE_TEXT)
        return

    await update_expense(session, expense, editor_id=member.id, **changes)
    await state.clear()
    await message.answer(f"✅ Оновлено.\n\n{format_expense_card(expense)}")
