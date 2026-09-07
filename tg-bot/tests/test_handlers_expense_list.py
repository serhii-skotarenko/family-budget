from datetime import datetime

from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.handlers.expense_list import cmd_list, show_expense
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


async def test_empty_list_explains_how_to_start(session, member, category, settings):
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings)

    assert "Витрат ще немає" in message.last_reply
    assert message.replies[-1][1].get("reply_markup") is None


async def test_list_shows_records_newest_first_with_index_buttons(
    session, household, member, category, settings
):
    await make(session, household, member, category, 100)
    await make(session, household, member, category, 200, description="кава")
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings)

    text, kwargs = message.replies[-1]
    assert "<b>1.</b>" in text and "<b>2.</b>" in text
    buttons = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["1", "2"]


async def test_list_respects_the_configured_limit(session, household, member, category, settings):
    for amount in range(1, 6):
        await make(session, household, member, category, amount)
    settings.recent_expenses_limit = 3
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings)

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
