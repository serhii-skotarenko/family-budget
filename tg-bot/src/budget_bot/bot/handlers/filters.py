"""/filter: period → category → author, then the matching list."""

from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import FilterCb
from budget_bot.bot.keyboards import (
    BTN_FILTER,
    cancel_keyboard,
    expense_index_keyboard,
    filter_categories_keyboard,
    filter_members_keyboard,
    filter_periods_keyboard,
)
from budget_bot.bot.texts import EMPTY_RESULT_TEXT
from budget_bot.clock import utcnow
from budget_bot.formatting import format_expense_list
from budget_bot.models import Member
from budget_bot.periods import Period, PeriodRange, parse_custom_range, period_range
from budget_bot.services.access import list_members
from budget_bot.services.categories import list_categories
from budget_bot.services.expenses import ExpenseFilters, list_expenses

MAX_FILTER_RESULTS = 30

router = Router(name="filters")


class FilterFlow(StatesGroup):
    choosing = State()
    custom_range = State()


@router.message(Command("filter"))
@router.message(F.text == BTN_FILTER)
async def cmd_filter(message: Message, state: FSMContext) -> None:
    await state.set_state(FilterFlow.choosing)
    await state.set_data({})
    await message.answer("Оберіть період:", reply_markup=filter_periods_keyboard())


@router.callback_query(FilterFlow.choosing, FilterCb.filter(F.step == "period"))
async def choose_period(
    callback: CallbackQuery,
    callback_data: FilterCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    if callback_data.value == "custom":
        await state.set_state(FilterFlow.custom_range)
        await callback.message.answer(
            "Введіть діапазон у форматі ДД.ММ.РРРР-ДД.ММ.РРРР:",
            reply_markup=cancel_keyboard(),
        )
        await callback.answer()
        return

    await state.update_data(period=callback_data.value)
    await _ask_category(callback.message, session, member)
    await callback.answer()


@router.message(FilterFlow.custom_range)
async def enter_custom_range(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    raw = (message.text or "").strip()
    try:
        parse_custom_range(raw)
    except ValueError as error:
        await message.answer(f"⚠️ {escape(str(error))}", reply_markup=cancel_keyboard())
        return

    await state.update_data(period="custom", custom_range=raw)
    await state.set_state(FilterFlow.choosing)
    await _ask_category(message, session, member)


@router.callback_query(FilterFlow.choosing, FilterCb.filter(F.step == "category"))
async def choose_category(
    callback: CallbackQuery,
    callback_data: FilterCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    value = callback_data.value
    await state.update_data(category_id=None if value == "all" else int(value))
    members = await list_members(session, member.household_id)
    await callback.message.answer("Оберіть автора:", reply_markup=filter_members_keyboard(members))
    await callback.answer()


@router.callback_query(FilterFlow.choosing, FilterCb.filter(F.step == "member"))
async def choose_member(
    callback: CallbackQuery,
    callback_data: FilterCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    value = callback_data.value
    data = await state.update_data(member_id=None if value == "all" else int(value))
    await state.clear()

    period = _resolve_period(data)
    expenses = await list_expenses(
        session,
        member.household_id,
        ExpenseFilters(
            period=period,
            category_id=data.get("category_id"),
            member_id=data.get("member_id"),
            limit=MAX_FILTER_RESULTS,
        ),
    )
    header = "Знайдені витрати" if period is None else f"Витрати — {period.label}"
    await callback.message.answer(
        format_expense_list(expenses, header, EMPTY_RESULT_TEXT),
        reply_markup=expense_index_keyboard(expenses) if expenses else None,
    )
    await callback.answer()


async def _ask_category(message: Message, session: AsyncSession, member: Member) -> None:
    categories = await list_categories(session, member.household_id)
    await message.answer("Оберіть категорію:", reply_markup=filter_categories_keyboard(categories))


def _resolve_period(data: dict[str, Any]) -> PeriodRange | None:
    value = data.get("period")
    if value is None:
        return None
    if value == "custom":
        return parse_custom_range(data["custom_range"])
    return period_range(Period(value), utcnow())
