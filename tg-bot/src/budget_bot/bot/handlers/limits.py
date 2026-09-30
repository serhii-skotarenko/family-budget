"""/setlimit: period → category (or general) → amount. /limits lives here too (Task 6)."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.amounts import AmountError, format_amount, parse_amount
from budget_bot.bot.callbacks import LimitCb
from budget_bot.bot.keyboards import (
    cancel_keyboard,
    limit_categories_keyboard,
    limit_periods_keyboard,
)
from budget_bot.bot.predicates import NOT_A_COMMAND
from budget_bot.bot.replies import edit_or_answer
from budget_bot.clock import utcnow
from budget_bot.formatting import format_limit_saved
from budget_bot.models import Member
from budget_bot.periods import LIMIT_PERIOD_TITLES, Period
from budget_bot.services.categories import get_category, list_categories
from budget_bot.services.limits import GENERAL_LIMIT_NAME, get_active_limit, set_limit

router = Router(name="limits")

PERIOD_PROMPT = "Оберіть період ліміту:"


class SetLimit(StatesGroup):
    period = State()
    category = State()
    amount = State()


@router.message(Command("setlimit"))
async def cmd_setlimit(message: Message, state: FSMContext) -> None:
    await state.set_state(SetLimit.period)
    await state.set_data({})
    await message.answer(PERIOD_PROMPT, reply_markup=limit_periods_keyboard())


@router.callback_query(LimitCb.filter(F.action == "add"))
async def cb_add_limit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SetLimit.period)
    await state.set_data({})
    await callback.message.answer(PERIOD_PROMPT, reply_markup=limit_periods_keyboard())
    await callback.answer()


@router.callback_query(SetLimit.period, LimitCb.filter(F.action == "period"))
async def pick_limit_period(
    callback: CallbackQuery,
    callback_data: LimitCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    period_type = Period(callback_data.period_type)
    await state.set_state(SetLimit.category)
    categories = await list_categories(session, member.household_id)
    await edit_or_answer(
        callback,
        f"Ліміт на {LIMIT_PERIOD_TITLES[period_type]}. Оберіть категорію:",
        reply_markup=limit_categories_keyboard(period_type, categories),
    )
    await callback.answer()


@router.callback_query(SetLimit.category, LimitCb.filter(F.action == "category"))
async def pick_limit_category(
    callback: CallbackQuery,
    callback_data: LimitCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    period_type = Period(callback_data.period_type)
    if callback_data.category_id == 0:
        category_id, name = None, GENERAL_LIMIT_NAME
    else:
        category = await get_category(session, member.household_id, callback_data.category_id)
        if category is None:
            await callback.answer("Категорію не знайдено. Оберіть іншу.", show_alert=True)
            return
        category_id, name = category.id, category.name

    await ask_limit_amount(callback, state, session, member, period_type, category_id, name)
    await callback.answer()


async def ask_limit_amount(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
    period_type: Period,
    category_id: int | None,
    name: str,
) -> None:
    """Move to the amount step; shared by /setlimit and the ✏️ button in /limits."""
    await state.set_state(SetLimit.amount)
    await state.set_data(
        {"period_type": period_type.value, "category_id": category_id, "category_name": name}
    )
    current = await get_active_limit(
        session, member.household_id, period_type, category_id, utcnow()
    )
    hint = f" (зараз: {format_amount(current.amount)})" if current is not None else ""
    await callback.message.answer(
        f"Ліміт на {LIMIT_PERIOD_TITLES[period_type]} · <b>{escape(name)}</b>\n\n"
        f"Введіть суму ліміту в гривнях{hint}:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SetLimit.amount, NOT_A_COMMAND)
async def enter_limit_amount(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        amount = parse_amount(message.text or "")
    except AmountError as error:
        await message.answer(f"⚠️ {escape(str(error))}", reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    period_type = Period(data["period_type"])
    category_id = data["category_id"]
    previous = await get_active_limit(
        session, member.household_id, period_type, category_id, utcnow()
    )
    await state.clear()
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=period_type,
        category_id=category_id,
        amount=amount,
    )
    await message.answer(
        format_limit_saved(
            period_type,
            data["category_name"],
            amount,
            previous.amount if previous is not None else None,
        )
    )
