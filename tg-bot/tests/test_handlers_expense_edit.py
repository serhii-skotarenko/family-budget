from budget_bot.bot.callbacks import CategoryCb, EditFieldCb, ExpenseCb
from budget_bot.bot.handlers.expense_edit import (
    EditExpense,
    cb_edit_menu,
    cb_pick_field,
    enter_new_amount,
    enter_new_description,
    pick_new_category,
)
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense, get_expense
from tests.conftest import FakeCallback, FakeMessage


async def make(session, household, member, category, amount=250, description="кава"):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        description=description,
    )


async def test_edit_menu_offers_three_fields(session, household, member, category):
    expense = await make(session, household, member, category)
    callback = FakeCallback()

    await cb_edit_menu(
        callback,
        callback_data=ExpenseCb(action="edit", expense_id=expense.id),
        session=session,
        member=member,
    )

    labels = [
        button.text
        for row in callback.message.replies[-1][1]["reply_markup"].inline_keyboard
        for button in row
    ]
    assert any("Сума" in label for label in labels)
    assert any("Категорі" in label for label in labels)
    assert any("Опис" in label for label in labels)


async def test_partner_edits_amount_without_changing_the_author(
    session, household, member, partner, category, state
):
    expense = await make(session, household, member, category)

    await cb_pick_field(
        FakeCallback(),
        callback_data=EditFieldCb(field="amount", expense_id=expense.id),
        state=state,
        session=session,
        member=partner,
    )
    assert await state.get_state() == EditExpense.amount

    message = FakeMessage(text="300")
    await enter_new_amount(message, state=state, session=session, member=partner)

    updated = await get_expense(session, household.id, expense.id)
    assert updated.amount == 300
    assert updated.member_id == member.id
    assert updated.updated_by_id == partner.id
    assert "Змінив(ла): Оля" in message.last_reply
    assert await state.get_state() is None


async def test_invalid_new_amount_keeps_state(session, household, member, category, state):
    expense = await make(session, household, member, category)
    await state.set_state(EditExpense.amount)
    await state.update_data(expense_id=expense.id)

    message = FakeMessage(text="-5")
    await enter_new_amount(message, state=state, session=session, member=member)

    assert await state.get_state() == EditExpense.amount
    assert (await get_expense(session, household.id, expense.id)).amount == 250


async def test_edit_description_and_clearing_it(session, household, member, category, state):
    expense = await make(session, household, member, category)
    await state.set_state(EditExpense.description)
    await state.update_data(expense_id=expense.id)

    await enter_new_description(
        FakeMessage(text="обід"), state=state, session=session, member=member
    )
    assert (await get_expense(session, household.id, expense.id)).description == "обід"

    await state.set_state(EditExpense.description)
    await state.update_data(expense_id=expense.id)
    await enter_new_description(FakeMessage(text="-"), state=state, session=session, member=member)
    assert (await get_expense(session, household.id, expense.id)).description is None


async def test_edit_category(session, household, member, category, state):
    expense = await make(session, household, member, category)
    coffee = await add_category(session, household.id, "Кава")
    await state.set_state(EditExpense.category)
    await state.update_data(expense_id=expense.id)

    await pick_new_category(
        FakeCallback(),
        callback_data=CategoryCb(action="edit", category_id=coffee.id),
        state=state,
        session=session,
        member=member,
    )

    updated = await get_expense(session, household.id, expense.id)
    assert updated.category_id == coffee.id
    assert await state.get_state() is None


async def test_editing_a_deleted_expense_reports_alert(session, member, category, state):
    callback = FakeCallback()

    await cb_edit_menu(
        callback,
        callback_data=ExpenseCb(action="edit", expense_id=999),
        session=session,
        member=member,
    )

    assert callback.answers[-1][1] is True
