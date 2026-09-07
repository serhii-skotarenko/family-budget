"""Deleting an expense, always behind an explicit confirmation."""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.keyboards import delete_confirm_keyboard
from budget_bot.bot.replies import edit_or_answer
from budget_bot.bot.texts import MISSING_EXPENSE_TEXT
from budget_bot.formatting import format_expense_card
from budget_bot.models import Member
from budget_bot.services.expenses import delete_expense, get_expense

router = Router(name="expense_delete")


@router.callback_query(ExpenseCb.filter(F.action == "delete"))
async def cb_ask_delete(
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
        f"Видалити цей запис?\n\n{format_expense_card(expense)}",
        reply_markup=delete_confirm_keyboard(expense.id),
    )
    await callback.answer()


@router.callback_query(ExpenseCb.filter(F.action == "delete_yes"))
async def cb_do_delete(
    callback: CallbackQuery,
    callback_data: ExpenseCb,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await delete_expense(session, expense)
    await edit_or_answer(callback, "🗑 Запис видалено.")
    await callback.answer()
