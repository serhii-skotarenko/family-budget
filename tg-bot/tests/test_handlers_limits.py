from budget_bot.bot.callbacks import LimitCb
from budget_bot.bot.handlers.add_expense import AddExpense
from budget_bot.bot.handlers.limits import (
    SetLimit,
    cb_ask_delete_limit,
    cb_delete_limit,
    cb_edit_limit,
    cb_keep_limit,
    cmd_limits,
    cmd_setlimit,
    enter_limit_amount,
    pick_limit_category,
    pick_limit_period,
)
from budget_bot.clock import utcnow
from budget_bot.periods import Period
from budget_bot.services.expenses import create_expense
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


async def _set(session, member, period, category_id, amount):
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=period,
        category_id=category_id,
        amount=amount,
    )


async def test_limits_empty(session, member, state):
    message = FakeMessage(text="/limits")

    await cmd_limits(message, state=state, session=session, member=member)

    assert "Лімітів ще немає" in message.last_reply
    assert buttons(message.replies[-1][1]) == ["➕ Додати ліміт"]


async def test_limits_shows_progress_and_buttons(session, household, member, category, state):
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=9800,
    )
    await _set(session, member, Period.MONTH, category.id, 12000)
    await _set(session, member, Period.WEEK, None, 20000)
    message = FakeMessage(text="/limits")

    await cmd_limits(message, state=state, session=session, member=member)

    assert "9 800 ₴ / 12 000 ₴" in message.last_reply
    assert buttons(message.replies[-1][1]) == [
        "✏️ Їжа · міс",
        "🗑",
        "✏️ Загальний · тиж",
        "🗑",
        "➕ Додати ліміт",
    ]


async def test_edit_button_jumps_to_amount_step(session, member, category, state):
    await _set(session, member, Period.MONTH, category.id, 12000)
    callback = FakeCallback()

    await cb_edit_limit(
        callback,
        callback_data=LimitCb(action="edit", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )

    assert await state.get_state() == SetLimit.amount
    assert "(зараз: 12 000 ₴)" in callback.message.last_reply

    reply = FakeMessage(text="15000")
    await enter_limit_amount(reply, state=state, session=session, member=member)
    assert "(було 12 000 ₴)" in reply.last_reply


async def test_delete_asks_then_removes_and_rerenders(session, member, category, state):
    await _set(session, member, Period.MONTH, category.id, 12000)
    ask = FakeCallback()

    await cb_ask_delete_limit(
        ask,
        callback_data=LimitCb(action="delete", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    assert "Зняти ліміт «Їжа · місяць»?" in ask.message.last_reply

    confirm = FakeCallback()
    await cb_delete_limit(
        confirm,
        callback_data=LimitCb(action="delete_yes", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    assert confirm.message.last_edit.startswith("🗑 Ліміт знято.")
    assert "Лімітів ще немає" in confirm.message.last_edit
    assert await active_limits(session, member.household_id, utcnow()) == []


async def test_double_tap_delete_reports_already_removed(session, member, category, state):
    await _set(session, member, Period.MONTH, None, 12000)
    data = LimitCb(action="delete_yes", period_type="month", category_id=0)
    await cb_delete_limit(
        FakeCallback(), callback_data=data, state=state, session=session, member=member
    )
    second = FakeCallback()

    await cb_delete_limit(second, callback_data=data, state=state, session=session, member=member)

    assert second.answers[-1] == ("Ліміт уже знято.", True)
    assert second.message.edits == []


async def test_edit_of_removed_limit_is_stale(session, member, category, state):
    callback = FakeCallback()

    await cb_edit_limit(
        callback,
        callback_data=LimitCb(action="edit", period_type="week", category_id=0),
        state=state,
        session=session,
        member=member,
    )

    assert callback.answers[-1] == ("Ліміт уже знято.", True)
    assert await state.get_state() is None


async def test_declining_removal_keeps_an_unrelated_dialog(session, member, category, state):
    await _set(session, member, Period.MONTH, category.id, 12000)
    ask = FakeCallback()
    await cb_ask_delete_limit(
        ask,
        callback_data=LimitCb(action="delete", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    no_button = buttons(ask.message.replies[-1][1]).index("↩️ Ні")
    no_data = ask.message.replies[-1][1]["reply_markup"].inline_keyboard[0][no_button].callback_data
    # Meanwhile the user started /add and is mid-dialog.
    await state.set_state(AddExpense.category)
    await state.update_data(amount=250)
    decline = FakeCallback()

    await cb_keep_limit(decline, callback_data=LimitCb.unpack(no_data), state=state)

    assert await state.get_state() == AddExpense.category
    assert (await state.get_data())["amount"] == 250
    assert decline.message.last_edit == "Ліміт залишено без змін."
    assert await get_active_limit(session, member.household_id, Period.MONTH, category.id, utcnow())
