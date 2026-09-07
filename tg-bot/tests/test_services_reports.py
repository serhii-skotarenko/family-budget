from datetime import datetime

from budget_bot.periods import Period, period_range
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense
from budget_bot.services.reports import build_report

NOW = datetime(2026, 9, 9, 9, 0)  # Wednesday 12:00 Kyiv
WEEK = period_range(Period.WEEK, NOW)


async def add(session, household, member, category, amount, when=NOW):
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        created_at=when,
    )


async def test_empty_period_reports_zero(session, household, member, category):
    report = await build_report(session, household.id, WEEK)

    assert report.total == 0
    assert report.by_category == []
    assert report.by_member == []
    assert report.period_label == WEEK.label


async def test_totals_and_shares(session, household, member, partner, category):
    coffee = await add_category(session, household.id, "Кава")
    await add(session, household, member, category, 600)
    await add(session, household, partner, category, 200)
    await add(session, household, partner, coffee, 200)

    report = await build_report(session, household.id, WEEK)

    assert report.total == 1000
    assert [(c.name, c.amount, c.share) for c in report.by_category] == [
        ("Їжа", 800, 80.0),
        ("Кава", 200, 20.0),
    ]
    assert [(m.display_name, m.amount) for m in report.by_member] == [
        ("Сергій", 600),
        ("Оля", 400),
    ]


async def test_expenses_outside_the_period_are_excluded(session, household, member, category):
    await add(session, household, member, category, 100, when=WEEK.start)
    await add(session, household, member, category, 999, when=WEEK.end)

    report = await build_report(session, household.id, WEEK)

    assert report.total == 100


async def test_categories_are_sorted_by_amount_desc(session, household, member, category):
    small = await add_category(session, household.id, "Мале")
    big = await add_category(session, household.id, "Велике")
    await add(session, household, member, small, 10)
    await add(session, household, member, big, 90)

    report = await build_report(session, household.id, WEEK)

    assert [c.name for c in report.by_category] == ["Велике", "Мале"]
