from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.handlers.expense_delete import cb_ask_delete, cb_do_delete
from budget_bot.clock import utcnow
from budget_bot.periods import Period, period_range
from budget_bot.services.expenses import create_expense, get_expense, list_expenses
from budget_bot.services.reports import build_report
from tests.conftest import FakeCallback


async def make(session, household, member, category, amount=250):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
    )


async def test_delete_asks_for_confirmation_first(session, household, member, category):
    expense = await make(session, household, member, category)
    callback = FakeCallback()

    await cb_ask_delete(
        callback,
        callback_data=ExpenseCb(action="delete", expense_id=expense.id),
        session=session,
        member=member,
    )

    text, kwargs = callback.message.replies[-1]
    assert "Видалити" in text
    labels = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any("Так" in label for label in labels)
    assert any("Ні" in label for label in labels)
    assert await get_expense(session, household.id, expense.id) is not None


async def test_confirmed_delete_removes_from_lists_and_reports(
    session, household, member, category
):
    expense = await make(session, household, member, category, amount=250)
    callback = FakeCallback()

    await cb_do_delete(
        callback,
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense.id),
        session=session,
        member=member,
    )

    assert await get_expense(session, household.id, expense.id) is None
    assert await list_expenses(session, household.id) == []
    report = await build_report(session, household.id, period_range(Period.YEAR, utcnow()))
    assert report.total == 0
    assert len(callback.message.edits) == 1
    assert "видалено" in callback.message.last_edit


async def test_partner_can_delete_someone_elses_expense(
    session, household, member, partner, category
):
    expense = await make(session, household, member, category)

    await cb_do_delete(
        FakeCallback(),
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense.id),
        session=session,
        member=partner,
    )

    assert await get_expense(session, household.id, expense.id) is None


async def test_deleting_twice_reports_alert(session, household, member, category):
    expense = await make(session, household, member, category)
    await cb_do_delete(
        FakeCallback(),
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense.id),
        session=session,
        member=member,
    )

    second = FakeCallback()
    await cb_do_delete(
        second,
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense.id),
        session=session,
        member=member,
    )

    assert second.answers[-1][1] is True
    assert second.message.edits == []
