from budget_bot.bot.callbacks import CategoryCb
from budget_bot.bot.handlers.add_expense import (
    AddExpense,
    enter_amount,
    enter_description,
    pick_category,
    save_expense,
    skip_description,
    start_add,
)
from budget_bot.services.expenses import list_expenses
from tests.conftest import FakeCallback, FakeMessage


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
