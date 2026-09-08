"""/list: recent expenses plus the per-record card."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.keyboards import BTN_LIST, expense_card_keyboard, expense_index_keyboard
from budget_bot.bot.texts import EMPTY_LIST_TEXT, MISSING_EXPENSE_TEXT
from budget_bot.config import Settings
from budget_bot.formatting import format_expense_card, format_expense_list
from budget_bot.models import Member
from budget_bot.services.expenses import ExpenseFilters, get_expense, list_expenses

router = Router(name="expense_list")


@router.message(Command("list"))
@router.message(F.text == BTN_LIST)
async def cmd_list(
    message: Message,
    session: AsyncSession,
    member: Member,
    settings: Settings,
    state: FSMContext,
) -> None:
    await state.clear()
    expenses = await list_expenses(
        session, member.household_id, ExpenseFilters(limit=settings.recent_expenses_limit)
    )
    await message.answer(
        format_expense_list(expenses, "Останні витрати", EMPTY_LIST_TEXT),
        reply_markup=expense_index_keyboard(expenses) if expenses else None,
    )


@router.callback_query(ExpenseCb.filter(F.action == "view"))
async def show_expense(
    callback: CallbackQuery,
    callback_data: ExpenseCb,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await callback.message.answer(
        format_expense_card(expense), reply_markup=expense_card_keyboard(expense.id)
    )
    await callback.answer()
