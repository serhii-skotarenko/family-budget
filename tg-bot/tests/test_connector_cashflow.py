from datetime import date

import pytest
import pytest_asyncio

from budget_bot.connector.analytics import budget_overview, cashflow_report
from budget_bot.connector.inputs import DateRange, InvalidRequest
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)


@pytest_asyncio.fixture
async def incomes(september_one_time, budget_writer) -> None:
    """300 000 from 05.09, 312 000 from 02.10; one October expense of 3 000."""
    await budget_writer.set_income(amount=300000, at=kyiv(2026, 9, 5))
    await budget_writer.set_income(amount=312000, at=kyiv(2026, 10, 2))
    await budget_writer.add_expense(category="Їжа", member="Оля", amount=3000, at=kyiv(2026, 10, 3))


async def report(session_factory, first, last):
    async with session_factory() as session:
        return await cashflow_report(session, DateRange(first, last), now_utc=NOW)


async def test_whole_months_with_income_from_when_it_was_set(incomes, readonly_session_factory):
    result = await report(readonly_session_factory, date(2026, 8, 10), date(2026, 12, 31))

    assert [month.model_dump() for month in result.months] == [
        {
            "month_start": date(2026, 8, 1),
            "month_end": date(2026, 8, 31),
            "income": None,
            "spent": 350,
            "one_time_amount": 0,
            "free_cashflow": None,
            "complete": True,
        },
        {
            # 250 + 100 + 1200 + 600 regular, 5000 + 300 one-time.
            "month_start": date(2026, 9, 1),
            "month_end": date(2026, 9, 30),
            "income": 300000,
            "spent": 7450,
            "one_time_amount": 5300,
            "free_cashflow": 292550,
            "complete": True,
        },
        {
            "month_start": date(2026, 10, 1),
            "month_end": date(2026, 10, 31),
            "income": 312000,
            "spent": 3000,
            "one_time_amount": 0,
            "free_cashflow": 309000,
            "complete": False,
        },
    ]


async def test_range_in_the_future_is_empty(incomes, readonly_session_factory):
    result = await report(readonly_session_factory, date(2026, 11, 1), date(2026, 12, 31))

    assert result.months == []


async def test_too_many_months_is_rejected(readonly_session_factory):
    with pytest.raises(InvalidRequest, match="max 60"):
        await report(readonly_session_factory, date(2020, 1, 1), date(2026, 10, 1))


async def test_overview_carries_the_current_income(incomes, readonly_session_factory):
    async with readonly_session_factory() as session:
        now_income = await budget_overview(session, now_utc=NOW)
        before = await budget_overview(session, now_utc=kyiv(2026, 9, 1))

    assert now_income.current_monthly_income == 312000
    assert before.current_monthly_income is None
