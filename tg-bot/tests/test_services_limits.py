from datetime import timedelta

from budget_bot.periods import Period, period_range
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense
from budget_bot.services.limits import (
    LimitStatus,
    active_limits,
    forecast,
    get_active_limit,
    limit_progress,
    limit_status,
    period_days,
    progress_for_expense,
    remove_limit,
    set_limit,
)
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)  # Thursday; week 12.10–18.10, month day 15 of 31


async def spend(session, household, member, category, amount, when=NOW, one_time=False):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        is_one_time=one_time,
        created_at=when,
    )


async def limit(session, household, member, period, category, amount, when=NOW):
    return await set_limit(
        session,
        household_id=household.id,
        member_id=member.id,
        period_type=period,
        category_id=category.id if category else None,
        amount=amount,
        now=when,
    )


def test_forecast():
    assert forecast(1000, 1, 31) == 31000
    assert forecast(1000, 31, 31) == 1000
    assert forecast(100, 3, 7) == 233  # 100 / 3 * 7 = 233.3
    assert forecast(0, 15, 31) == 0


def test_period_days():
    assert period_days(period_range(Period.MONTH, NOW), NOW) == (15, 31)
    assert period_days(period_range(Period.WEEK, NOW), NOW) == (4, 7)
    feb = kyiv(2026, 2, 10)
    assert period_days(period_range(Period.MONTH, feb), feb) == (10, 28)
    first_minute = kyiv(2026, 10, 1, 0, 5)
    assert period_days(period_range(Period.MONTH, first_minute), first_minute) == (1, 31)


def test_limit_status():
    assert limit_status(79, 900, 1000) is LimitStatus.OK
    assert limit_status(80, 900, 1000) is LimitStatus.WARN
    assert limit_status(50, 1001, 1000) is LimitStatus.WARN
    assert limit_status(100, 1000, 1000) is LimitStatus.OVER


async def test_active_limit_follows_history(session, household, member, category):
    t1 = NOW - timedelta(days=3)
    await limit(session, household, member, Period.MONTH, category, 1000, when=t1)
    await limit(
        session, household, member, Period.MONTH, category, 2000, when=t1 + timedelta(hours=1)
    )

    active = await get_active_limit(session, household.id, Period.MONTH, category.id, NOW)
    assert active.amount == 2000

    removed = await remove_limit(
        session,
        household_id=household.id,
        member_id=member.id,
        period_type=Period.MONTH,
        category_id=category.id,
        now=t1 + timedelta(hours=2),
    )
    assert removed is True
    assert await get_active_limit(session, household.id, Period.MONTH, category.id, NOW) is None
    assert await active_limits(session, household.id, NOW) == []

    await limit(
        session, household, member, Period.MONTH, category, 3000, when=t1 + timedelta(hours=3)
    )
    active = await get_active_limit(session, household.id, Period.MONTH, category.id, NOW)
    assert active.amount == 3000


async def test_limit_set_in_the_future_is_not_active_yet(session, household, member, category):
    await limit(
        session, household, member, Period.MONTH, category, 1000, when=NOW + timedelta(hours=1)
    )

    assert await active_limits(session, household.id, NOW) == []


async def test_remove_without_active_limit_is_a_no_op(session, household, member, category):
    removed = await remove_limit(
        session,
        household_id=household.id,
        member_id=member.id,
        period_type=Period.WEEK,
        category_id=None,
        now=NOW,
    )

    assert removed is False


async def test_progress_counts_the_whole_period_regular_only(session, household, member, category):
    coffee = await add_category(session, household.id, "Кава")
    await spend(session, household, member, category, 3000, when=kyiv(2026, 10, 2))
    await spend(session, household, member, category, 5000, one_time=True)
    await spend(session, household, member, coffee, 700)
    await spend(session, household, member, category, 999, when=kyiv(2026, 9, 30, 23, 59))
    # Limits set mid-month still count expenses from 1 October.
    await limit(session, household, member, Period.MONTH, category, 10000)
    await limit(session, household, member, Period.MONTH, None, 20000)

    progress = await limit_progress(session, household.id, Period.MONTH, NOW)

    general, food = progress
    assert general.category_id is None and general.name == "Загальний"
    assert general.spent == 3700  # 3000 + 700; one-time and September excluded
    assert food.name == "Їжа"
    assert food.spent == 3000
    assert food.percent == 30
    assert food.remaining == 7000
    assert food.forecast == 6200  # 3000 / 15 * 31
    assert food.status is LimitStatus.OK


async def test_limit_without_spending_shows_zero(session, household, member, category):
    await limit(session, household, member, Period.WEEK, category, 1000)

    (progress,) = await limit_progress(session, household.id, Period.WEEK, NOW)

    assert (progress.spent, progress.percent, progress.forecast) == (0, 0, 0)
    assert progress.status is LimitStatus.OK


async def test_progress_for_expense_returns_only_relevant_limits(
    session, household, member, category
):
    coffee = await add_category(session, household.id, "Кава")
    await limit(session, household, member, Period.MONTH, category, 10000)
    await limit(session, household, member, Period.WEEK, None, 5000)
    await limit(session, household, member, Period.MONTH, coffee, 1000)
    expense = await spend(session, household, member, category, 4500)

    progress = await progress_for_expense(session, expense, NOW)

    assert [(p.period_type, p.category_id) for p in progress] == [
        (Period.MONTH, category.id),
        (Period.WEEK, None),
    ]
    assert progress[1].percent == 90


async def test_progress_for_one_time_expense_is_empty(session, household, member, category):
    await limit(session, household, member, Period.MONTH, category, 100)
    expense = await spend(session, household, member, category, 4500, one_time=True)

    assert await progress_for_expense(session, expense, NOW) == []
