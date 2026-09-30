from budget_bot.bot.callbacks import CategoryCb
from budget_bot.bot.handlers.add_expense import (
    AddExpense,
    enter_amount,
    enter_description,
    pick_category,
    save_expense,
    skip_description,
    start_add,
    toggle_one_time,
)
from budget_bot.periods import Period
from budget_bot.services.expenses import create_expense, list_expenses
from budget_bot.services.limits import set_limit
from tests.conftest import FakeCallback, FakeMessage


async def test_start_add_resets_leftover_state_data(state):
    await state.update_data(category_id=999, amount=100)

    await start_add(FakeMessage(text="/add"), state=state)

    assert await state.get_data() == {}


async def test_full_flow_saves_expense_with_description(session, member, category, state):
    await start_add(FakeMessage(text="/add"), state=state)
    assert await state.get_state() == AddExpense.amount

    await enter_amount(FakeMessage(text="250"), state=state, session=session, member=member)
    assert await state.get_state() == AddExpense.category

    callback = FakeCallback()
    await pick_category(
        callback,
        callback_data=CategoryCb(action="pick", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    assert await state.get_state() == AddExpense.description

    await enter_description(FakeMessage(text="кава"), state=state)
    assert await state.get_state() == AddExpense.confirm

    confirm = FakeCallback()
    await save_expense(confirm, state=state, session=session, member=member)

    assert await state.get_state() is None
    saved = await list_expenses(session, member.household_id)
    assert len(saved) == 1
    assert saved[0].amount == 250
    assert saved[0].description == "кава"
    assert saved[0].member_id == member.id
    assert "Записано" in confirm.message.last_edit


async def test_description_can_be_skipped(session, member, category, state):
    await state.set_state(AddExpense.category)
    callback = FakeCallback()
    await pick_category(
        callback,
        callback_data=CategoryCb(action="pick", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    await state.update_data(amount=100)

    await skip_description(callback, state=state)
    assert await state.get_state() == AddExpense.confirm

    await save_expense(FakeCallback(), state=state, session=session, member=member)

    saved = await list_expenses(session, member.household_id)
    assert saved[0].description is None


async def test_invalid_amount_keeps_the_state_and_explains(session, member, category, state):
    await state.set_state(AddExpense.amount)
    message = FakeMessage(text="12.5")

    await enter_amount(message, state=state, session=session, member=member)

    assert await state.get_state() == AddExpense.amount
    assert "цілим числом" in message.last_reply
    assert await list_expenses(session, member.household_id) == []


async def test_zero_amount_is_rejected(session, member, category, state):
    await state.set_state(AddExpense.amount)
    message = FakeMessage(text="0")

    await enter_amount(message, state=state, session=session, member=member)

    assert await state.get_state() == AddExpense.amount
    assert "більшою за нуль" in message.last_reply


async def test_double_tap_save_inserts_exactly_once(session, member, category, state):
    await state.set_state(AddExpense.confirm)
    await state.update_data(amount=100, category_id=category.id, category_name=category.name)

    first = FakeCallback()
    await save_expense(first, state=state, session=session, member=member)
    assert await state.get_state() is None
    assert "Записано" in first.message.last_edit

    second = FakeCallback()
    await save_expense(second, state=state, session=session, member=member)

    saved = await list_expenses(session, member.household_id)
    assert len(saved) == 1
    assert second.message.edits == []
    assert "уже збережено" in second.answers[-1][0].lower()


async def test_unknown_category_is_reported(session, member, category, state):
    await state.set_state(AddExpense.category)
    await state.update_data(amount=100)
    callback = FakeCallback()

    await pick_category(
        callback,
        callback_data=CategoryCb(action="pick", category_id=999),
        state=state,
        session=session,
        member=member,
    )

    assert callback.answers[-1][1] is True  # show_alert
    assert await state.get_state() == AddExpense.category


def labels(kwargs) -> list[str]:
    return [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]


async def _history(session, household, member, category, amounts):
    for amount in amounts:
        await create_expense(
            session,
            household_id=household.id,
            member_id=member.id,
            category_id=category.id,
            amount=amount,
        )


async def _reach_confirmation(session, member, category, state, amount):
    await state.set_state(AddExpense.category)
    await state.update_data(amount=amount)
    callback = FakeCallback()
    await pick_category(
        callback,
        callback_data=CategoryCb(action="pick", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    await skip_description(callback, state=state)
    return callback


async def test_confirmation_has_one_time_toggle(session, member, category, state):
    callback = await _reach_confirmation(session, member, category, state, 100)

    text, kwargs = callback.message.replies[-1]
    assert "Перевірте запис" in text
    assert labels(kwargs)[0] == "☐ Разова"


async def test_toggle_flips_flag_and_rerenders(session, member, category, state):
    await _reach_confirmation(session, member, category, state, 100)
    toggle = FakeCallback()

    await toggle_one_time(toggle, state=state)

    assert (await state.get_data())["is_one_time"] is True
    assert labels(toggle.message.edits[-1][1])[0] == "☑ Разова"

    await toggle_one_time(toggle, state=state)
    assert (await state.get_data())["is_one_time"] is False


async def test_saving_a_one_time_expense(session, member, category, state):
    await _reach_confirmation(session, member, category, state, 100)
    await toggle_one_time(FakeCallback(), state=state)
    confirm = FakeCallback()

    await save_expense(confirm, state=state, session=session, member=member)

    saved = await list_expenses(session, member.household_id)
    assert saved[0].is_one_time is True
    assert "разова" in confirm.message.last_edit


async def test_anomalous_amount_warns_on_confirmation(session, household, member, category, state):
    await _history(session, household, member, category, [100, 100, 100, 100, 100])

    callback = await _reach_confirmation(session, member, category, state, 400)

    text = callback.message.last_reply
    assert "значно більша за типову для «Їжа» (звичайно ~100 ₴)" in text
    assert text.index("значно більша") < text.index("Перевірте запис")


async def test_no_anomaly_warning_with_too_little_history(
    session, household, member, category, state
):
    await _history(session, household, member, category, [100, 100, 100, 100])

    callback = await _reach_confirmation(session, member, category, state, 400)

    assert "значно більша" not in callback.message.last_reply


async def _month_limit(session, member, category, amount):
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=Period.MONTH,
        category_id=category.id,
        amount=amount,
    )


async def _save(session, member, category, state, amount, one_time=False):
    await state.set_state(AddExpense.confirm)
    await state.update_data(
        amount=amount, category_id=category.id, category_name=category.name, is_one_time=one_time
    )
    confirm = FakeCallback()
    await save_expense(confirm, state=state, session=session, member=member)
    return confirm.message.last_edit


async def test_limit_alert_after_save(session, household, member, category, state):
    await _history(session, household, member, category, [700])
    await _month_limit(session, member, category, 1000)

    text = await _save(session, member, category, state, 150)

    assert "⚠️ Їжа (місяць): 850 ₴ / 1 000 ₴ — 85%" in text


async def test_no_limit_alert_below_threshold_or_for_one_time(
    session, household, member, category, state
):
    await _month_limit(session, member, category, 1000)

    assert "Їжа (місяць)" not in await _save(session, member, category, state, 100)
    assert "Їжа (місяць)" not in await _save(session, member, category, state, 5000, one_time=True)
