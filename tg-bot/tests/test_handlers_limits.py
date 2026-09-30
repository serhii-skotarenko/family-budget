from budget_bot.bot.callbacks import LimitCb
from budget_bot.bot.handlers.limits import (
    SetLimit,
    cmd_setlimit,
    enter_limit_amount,
    pick_limit_category,
    pick_limit_period,
)
from budget_bot.clock import utcnow
from budget_bot.periods import Period
from budget_bot.services.limits import active_limits, get_active_limit, set_limit
from tests.conftest import FakeCallback, FakeMessage


def buttons(kwargs) -> list[str]:
    return [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]


async def run_setlimit(session, member, state, period: str, category_id: int, amount: str):
    await cmd_setlimit(FakeMessage(text="/setlimit"), state=state)
    await pick_limit_period(
        FakeCallback(),
        callback_data=LimitCb(action="period", period_type=period),
        state=state,
        session=session,
        member=member,
    )
    await pick_limit_category(
        FakeCallback(),
        callback_data=LimitCb(action="category", period_type=period, category_id=category_id),
        state=state,
        session=session,
        member=member,
    )
    reply = FakeMessage(text=amount)
    await enter_limit_amount(reply, state=state, session=session, member=member)
    return reply


async def test_setlimit_offers_week_and_month(state):
    message = FakeMessage(text="/setlimit")

    await cmd_setlimit(message, state=state)

    assert await state.get_state() == SetLimit.period
    labels = buttons(message.replies[-1][1])
    assert "Тиждень" in labels and "Місяць" in labels


async def test_category_step_offers_general_first(session, member, category, state):
    await cmd_setlimit(FakeMessage(text="/setlimit"), state=state)
    callback = FakeCallback()

    await pick_limit_period(
        callback,
        callback_data=LimitCb(action="period", period_type="month"),
        state=state,
        session=session,
        member=member,
    )

    assert await state.get_state() == SetLimit.category
    labels = buttons(callback.message.edits[-1][1])
    assert labels[0] == "🌐 Загальний"
    assert "Їжа" in labels


async def test_full_flow_saves_a_category_limit(session, member, category, state):
    reply = await run_setlimit(session, member, state, "month", category.id, "12 000")

    assert await state.get_state() is None
    saved = await get_active_limit(
        session, member.household_id, Period.MONTH, category.id, utcnow()
    )
    assert saved.amount == 12000
    assert saved.created_by_id == member.id
    assert reply.last_reply == "✅ Ліміт на місяць · Їжа: <b>12 000 ₴</b>"


async def test_general_limit_and_previous_amount(session, member, category, state):
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=Period.WEEK,
        category_id=None,
        amount=10000,
    )

    reply = await run_setlimit(session, member, state, "week", 0, "8000")

    assert reply.last_reply == ("✅ Ліміт на тиждень · Загальний: <b>8 000 ₴</b> (було 10 000 ₴)")


async def test_amount_prompt_shows_current_limit(session, member, category, state):
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=Period.MONTH,
        category_id=category.id,
        amount=5000,
    )
    await state.set_state(SetLimit.category)
    callback = FakeCallback()

    await pick_limit_category(
        callback,
        callback_data=LimitCb(action="category", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )

    assert await state.get_state() == SetLimit.amount
    assert "(зараз: 5 000 ₴)" in callback.message.last_reply


async def test_invalid_amount_keeps_the_step(session, member, category, state):
    await state.set_state(SetLimit.amount)
    await state.update_data(period_type="month", category_id=None, category_name="Загальний")
    message = FakeMessage(text="0")

    await enter_limit_amount(message, state=state, session=session, member=member)

    assert await state.get_state() == SetLimit.amount
    assert "більшою за нуль" in message.last_reply
    assert await active_limits(session, member.household_id, utcnow()) == []


async def test_unknown_category_is_reported(session, member, category, state):
    await state.set_state(SetLimit.category)
    callback = FakeCallback()

    await pick_limit_category(
        callback,
        callback_data=LimitCb(action="category", period_type="month", category_id=9999),
        state=state,
        session=session,
        member=member,
    )

    assert await state.get_state() == SetLimit.category
    assert callback.answers[-1][1] is True
