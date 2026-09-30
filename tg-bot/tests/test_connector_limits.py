from datetime import date

import pytest
import pytest_asyncio

from budget_bot.connector.analytics import limit_progress_report
from budget_bot.connector.inputs import InvalidRequest
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)  # Thursday; week 12.10–18.10, day 15 of October


@pytest_asyncio.fixture
async def limits_history(september_one_time, budget_writer) -> None:
    """September data from ``september_one_time`` plus limits and one October expense.

    - Їжа, month: 10 000 from 05.09, raised to 12 000 on 02.10.
    - General, week: 3 000 from 01.09.
    - 03.10: Їжа 3 000 (regular).
    """
    await budget_writer.set_limit(period="month", category="Їжа", amount=10000, at=kyiv(2026, 9, 5))
    await budget_writer.set_limit(
        period="month", category="Їжа", amount=12000, at=kyiv(2026, 10, 2)
    )
    await budget_writer.set_limit(period="week", category=None, amount=3000, at=kyiv(2026, 9, 1))
    await budget_writer.add_expense(category="Їжа", member="Оля", amount=3000, at=kyiv(2026, 10, 3))


async def report(session_factory, day):
    async with session_factory() as session:
        return await limit_progress_report(session, day, now_utc=NOW)


async def test_current_periods(limits_history, readonly_session_factory):
    result = await report(readonly_session_factory, date(2026, 10, 15))

    month, week = result.periods
    assert result.date == date(2026, 10, 15)
    assert (month.period_type, month.start_date, month.end_date) == (
        "month",
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    assert (month.day_index, month.days_in_period, month.complete) == (15, 31, False)
    assert [item.model_dump() for item in month.limits] == [
        {
            "category": "Їжа",
            "amount": 12000,
            "spent": 3000,
            "percent": 25,
            "remaining": 9000,
            "forecast": 6200,  # 3000 / 15 * 31
            "status": "ok",
        }
    ]
    assert (week.start_date, week.end_date, week.day_index, week.complete) == (
        date(2026, 10, 12),
        date(2026, 10, 18),
        4,
        False,
    )
    assert [(i.category, i.amount, i.spent, i.forecast) for i in week.limits] == [
        (None, 3000, 0, 0)
    ]


async def test_past_month_uses_the_limit_in_force_at_its_end(
    limits_history, readonly_session_factory
):
    result = await report(readonly_session_factory, date(2026, 9, 14))

    month, week = result.periods
    assert (month.start_date, month.end_date) == (date(2026, 9, 1), date(2026, 9, 30))
    assert (month.day_index, month.days_in_period, month.complete) == (30, 30, True)
    # 250 + 1200 regular Їжа in September; the 300 one-time and 31.08 are excluded.
    assert [(i.category, i.amount, i.spent, i.percent, i.forecast) for i in month.limits] == [
        ("Їжа", 10000, 1450, 14, 1450)
    ]
    # Week 14.09–20.09: 1200 (14.09 23:30) + 600 (15.09 00:10 Kyiv).
    assert (week.start_date, week.end_date, week.complete) == (
        date(2026, 9, 14),
        date(2026, 9, 20),
        True,
    )
    assert [(i.category, i.spent, i.percent, i.forecast, i.status) for i in week.limits] == [
        (None, 1800, 60, 1800, "ok")
    ]


async def test_no_limits_gives_empty_lists(early_september, readonly_session_factory):
    result = await report(readonly_session_factory, date(2026, 9, 14))

    assert [period.limits for period in result.periods] == [[], []]


async def test_future_date_is_rejected_with_today(readonly_session_factory):
    with pytest.raises(InvalidRequest, match="today in Kyiv is 2026-10-15"):
        await report(readonly_session_factory, date(2026, 10, 16))
