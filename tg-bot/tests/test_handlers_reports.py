from budget_bot.bot.callbacks import ReportCb
from budget_bot.bot.handlers.reports import cb_report, cmd_report
from budget_bot.clock import utcnow
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense
from tests.conftest import FakeCallback, FakeMessage


async def make(session, household, member, category, amount):
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        created_at=utcnow(),
    )


async def test_report_command_offers_week_month_year(state):
    message = FakeMessage(text="/report")

    await cmd_report(message, state=state)

    labels = [b.text for row in message.replies[-1][1]["reply_markup"].inline_keyboard for b in row]
    assert any("тиждень" in label.lower() for label in labels)
    assert any("місяць" in label.lower() for label in labels)
    assert any("рік" in label.lower() for label in labels)
    assert not any("сьогодні" in label.lower() for label in labels)


async def test_month_report_shows_totals_by_category_and_member(
    session, household, member, partner, category
):
    coffee = await add_category(session, household.id, "Кава")
    await make(session, household, member, category, 600)
    await make(session, household, partner, category, 200)
    await make(session, household, partner, coffee, 200)
    callback = FakeCallback()

    await cb_report(
        callback, callback_data=ReportCb(period="month"), session=session, member=member
    )

    text = callback.message.last_edit
    assert "Разом" in text
    assert "Їжа" in text and "80.0%" in text
    assert "Сергій" in text and "Оля" in text


async def test_empty_report_says_so_without_error(session, member, category):
    callback = FakeCallback()

    await cb_report(callback, callback_data=ReportCb(period="year"), session=session, member=member)

    assert "Витрат за цей період не знайдено" in callback.message.last_edit
