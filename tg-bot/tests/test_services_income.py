from datetime import date

from budget_bot.services.expenses import create_expense
from budget_bot.services.income import (
    cashflow,
    income_at,
    month_cashflow,
    month_income,
    month_range,
    next_month,
    set_income,
)
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)


async def income(session, household, member, amount, at):
    await set_income(session, household_id=household.id, member_id=member.id, amount=amount, now=at)


async def spend(session, household, member, category, amount, at, one_time=False):
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        is_one_time=one_time,
        created_at=at,
    )


def test_month_helpers():
    assert next_month(date(2026, 12, 1)) == date(2027, 1, 1)
    bounds = month_range(date(2026, 10, 1))
    assert (bounds.start, bounds.end) == (kyiv(2026, 10, 1, 0), kyiv(2026, 11, 1, 0))


async def test_no_income_yet(session, household):
    assert await income_at(session, household.id, NOW) is None
    assert await cashflow(session, household.id, date(2026, 1, 1), date(2026, 10, 1), NOW) is None


async def test_month_income_follows_history(session, household, member):
    await income(session, household, member, 300000, kyiv(2026, 9, 5))
    await income(session, household, member, 312000, kyiv(2026, 10, 20))  # after NOW

    # August: nothing yet. September: the version in force at its end.
    assert await month_income(session, household.id, date(2026, 8, 1), NOW) is None
    assert await month_income(session, household.id, date(2026, 9, 1), NOW) == 300000
    # October is current: a version from the future (20.10 > NOW) does not count yet.
    assert await month_income(session, household.id, date(2026, 10, 1), NOW) == 300000
    # November has not started.
    assert await month_income(session, household.id, date(2026, 11, 1), NOW) is None


async def test_change_mid_month_applies_to_the_whole_month(session, household, member):
    await income(session, household, member, 300000, kyiv(2026, 9, 5))
    await income(session, household, member, 312000, kyiv(2026, 10, 2))

    assert await month_income(session, household.id, date(2026, 9, 1), NOW) == 300000
    assert await month_income(session, household.id, date(2026, 10, 1), NOW) == 312000


async def test_month_cashflow_counts_all_expenses(session, household, member, category):
    await income(session, household, member, 300000, kyiv(2026, 9, 5))
    await spend(session, household, member, category, 2000, kyiv(2026, 9, 1, 0, 5))
    await spend(session, household, member, category, 500, kyiv(2026, 9, 30, 23, 50), True)
    await spend(session, household, member, category, 9999, kyiv(2026, 10, 1, 0, 1))

    september = await month_cashflow(session, household.id, date(2026, 9, 1), NOW)

    assert (september.income, september.spent, september.one_time) == (300000, 2500, 500)
    assert (september.free, september.complete) == (297500, True)
    october = await month_cashflow(session, household.id, date(2026, 10, 1), NOW)
    assert (october.spent, october.complete) == (9999, False)


async def test_year_cashflow_uses_only_months_with_income(session, household, member, category):
    await income(session, household, member, 300000, kyiv(2026, 9, 5))
    await income(session, household, member, 312000, kyiv(2026, 10, 2))
    await spend(session, household, member, category, 1000, kyiv(2026, 8, 10))  # no income yet
    await spend(session, household, member, category, 1500, kyiv(2026, 9, 10))
    await spend(session, household, member, category, 500, kyiv(2026, 9, 11), True)
    await spend(session, household, member, category, 3000, kyiv(2026, 10, 3))

    result = await cashflow(session, household.id, date(2026, 1, 1), date(2026, 12, 1), NOW)

    assert (result.first_month, result.months) == (date(2026, 9, 1), 2)
    assert (result.income, result.spent, result.free) == (612000, 5000, 607000)
