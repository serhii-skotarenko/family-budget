"""/setincome: the household's monthly income, one step."""

from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.amounts import AmountError, format_amount, parse_amount
from budget_bot.bot.keyboards import cancel_keyboard
from budget_bot.bot.predicates import NOT_A_COMMAND
from budget_bot.clock import utcnow
from budget_bot.formatting import format_income_saved
from budget_bot.models import Member
from budget_bot.services.income import income_at, set_income

router = Router(name="income")


class SetIncome(StatesGroup):
    amount = State()


@router.message(Command("setincome"))
async def cmd_setincome(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    await state.set_state(SetIncome.amount)
    await state.set_data({})
    current = await income_at(session, member.household_id, utcnow())
    hint = f" (зараз: {format_amount(current)})" if current is not None else ""
    await message.answer(
        f"💰 Введіть місячний дохід сім'ї в гривнях{hint}:", reply_markup=cancel_keyboard()
    )


@router.message(SetIncome.amount, NOT_A_COMMAND)
async def enter_income(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        amount = parse_amount(message.text or "")
    except AmountError as error:
        await message.answer(f"⚠️ {escape(str(error))}", reply_markup=cancel_keyboard())
        return

    now = utcnow()
    previous = await income_at(session, member.household_id, now)
    await state.clear()
    await set_income(
        session, household_id=member.household_id, member_id=member.id, amount=amount, now=now
    )
    await message.answer(format_income_saved(amount, previous, now))
