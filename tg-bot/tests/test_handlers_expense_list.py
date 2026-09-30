from datetime import datetime

from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.handlers.expense_list import cmd_list, show_expense, toggle_expense_one_time
from budget_bot.services.expenses import create_expense
from tests.conftest import FakeCallback, FakeMessage

NOW = datetime(2026, 9, 7, 9, 0)


async def make(session, household, member, category, amount, description=None):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        description=description,
        created_at=NOW,
    )


async def test_empty_list_explains_how_to_start(session, member, category, settings, state):
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings, state=state)

    assert "Витрат ще немає" in message.last_reply
    assert message.replies[-1][1].get("reply_markup") is None


async def test_list_shows_records_newest_first_with_index_buttons(
    session, household, member, category, settings, state
):
    await make(session, household, member, category, 100)
    await make(session, household, member, category, 200, description="кава")
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings, state=state)

    text, kwargs = message.replies[-1]
    assert "<b>1.</b>" in text and "<b>2.</b>" in text
    buttons = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["1", "2"]


async def test_list_respects_the_configured_limit(
    session, household, member, category, settings, state
):
    for amount in range(1, 6):
        await make(session, household, member, category, amount)
    settings.recent_expenses_limit = 3
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings, state=state)

    assert "<b>3.</b>" in message.last_reply
    assert "<b>4.</b>" not in message.last_reply


async def test_card_shows_details_and_actions(session, household, member, category):
    expense = await make(session, household, member, category, 250, description="кава")
    callback = FakeCallback()

    await show_expense(
        callback,
        callback_data=ExpenseCb(action="view", expense_id=expense.id),
        session=session,
        member=member,
    )

    text, kwargs = callback.message.replies[-1]
    assert f"Витрата #{expense.id}" in text
    assert "Автор: Сергій" in text
    labels = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any("Редагувати" in label for label in labels)
    assert any("Видалити" in label for label in labels)


async def test_card_for_missing_expense_reports_alert(session, member, category):
    callback = FakeCallback()

    await show_expense(
        callback,
        callback_data=ExpenseCb(action="view", expense_id=999),
        session=session,
        member=member,
    )

    assert callback.answers[-1][1] is True
    assert callback.message.replies == []


def card_buttons(kwargs) -> list[str]:
    return [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]


async def test_card_offers_mark_as_one_time(session, household, member, category):
    expense = await make(session, household, member, category, 100)
    callback = FakeCallback()

    await show_expense(
        callback,
        callback_data=ExpenseCb(action="view", expense_id=expense.id),
        session=session,
        member=member,
    )

    assert "🔁 Позначити як разову" in card_buttons(callback.message.replies[-1][1])


async def test_toggle_marks_and_unmarks(session, household, member, partner, category):
    expense = await make(session, household, member, category, 100)
    callback = FakeCallback()
    data = ExpenseCb(action="toggle_one_time", expense_id=expense.id)

    await toggle_expense_one_time(callback, callback_data=data, session=session, member=partner)

    text, kwargs = callback.message.edits[-1]
    assert "🔁 Разова витрата" in text
    assert "↩️ Зняти позначку разової" in card_buttons(kwargs)
    assert expense.is_one_time is True and expense.updated_by_id == partner.id

    await toggle_expense_one_time(callback, callback_data=data, session=session, member=member)

    assert expense.is_one_time is False
    assert "🔁 Разова витрата" not in callback.message.last_edit


async def test_toggle_on_missing_expense(session, member, category):
    callback = FakeCallback()

    await toggle_expense_one_time(
        callback,
        callback_data=ExpenseCb(action="toggle_one_time", expense_id=9999),
        session=session,
        member=member,
    )

    assert callback.answers[-1][1] is True
    assert callback.message.edits == []
