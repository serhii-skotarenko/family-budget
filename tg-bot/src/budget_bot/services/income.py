"""Monthly household income: append-only history and free cashflow for whole months.

A month uses the income in force at its last moment, or now for the current
month; free cashflow is that income minus all of the month's expenses,
one-time ones included.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.clock import utcnow
from budget_bot.models import Expense, Income
from budget_bot.periods import PeriodRange, kyiv_day_range, to_kyiv


def month_first(day: date) -> date:
    return day.replace(day=1)


def next_month(first: date) -> date:
    return (first + timedelta(days=32)).replace(day=1)


def month_range(first: date) -> PeriodRange:
    return kyiv_day_range(first, next_month(first) - timedelta(days=1))


async def set_income(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    amount: int,
    now: datetime | None = None,
) -> Income:
    now = now or utcnow()
    row = Income(
        household_id=household_id,
        amount=amount,
        effective_from=now,
        created_by_id=member_id,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def income_at(session: AsyncSession, household_id: int, as_of: datetime) -> int | None:
    return await session.scalar(
        select(Income.amount)
        .where(Income.household_id == household_id, Income.effective_from <= as_of)
        .order_by(Income.effective_from.desc(), Income.id.desc())
        .limit(1)
    )


async def month_income(
    session: AsyncSession, household_id: int, first: date, now: datetime
) -> int | None:
    bounds = month_range(first)
    if bounds.start > now:
        return None
    as_of = min(now, bounds.end - timedelta(microseconds=1))
    return await income_at(session, household_id, as_of)


@dataclass(frozen=True)
class MonthCashflow:
    first: date
    income: int | None
    spent: int  # all expenses of the month, one-time included
    one_time: int
    complete: bool

    @property
    def free(self) -> int | None:
        return None if self.income is None else self.income - self.spent


async def month_cashflow(
    session: AsyncSession, household_id: int, first: date, now: datetime
) -> MonthCashflow:
    bounds = month_range(first)
    spent, one_time = (
        await session.execute(
            select(
                func.coalesce(func.sum(Expense.amount), 0),
                func.coalesce(func.sum(case((Expense.is_one_time, Expense.amount), else_=0)), 0),
            ).where(
                Expense.household_id == household_id,
                Expense.created_at >= bounds.start,
                Expense.created_at < bounds.end,
            )
        )
    ).one()
    return MonthCashflow(
        first=first,
        income=await month_income(session, household_id, first, now),
        spent=int(spent),
        one_time=int(one_time),
        complete=now >= bounds.end,
    )


@dataclass(frozen=True)
class Cashflow:
    income: int
    spent: int
    first_month: date  # the first month whose income is counted
    months: int  # how many months had an income

    @property
    def free(self) -> int:
        return self.income - self.spent


async def cashflow(
    session: AsyncSession, household_id: int, first: date, last: date, now: datetime
) -> Cashflow | None:
    """Cashflow over the calendar months first..last (month starts), up to the current one.

    Only months with an income count, and only their expenses: spending from
    months before the income was set would otherwise skew the result.
    """
    current = month_first(to_kyiv(now).date())
    counted = []
    month = first
    while month <= last and month <= current:
        item = await month_cashflow(session, household_id, month, now)
        if item.income is not None:
            counted.append(item)
        month = next_month(month)
    if not counted:
        return None
    return Cashflow(
        income=sum(item.income for item in counted),
        spent=sum(item.spent for item in counted),
        first_month=counted[0].first,
        months=len(counted),
    )
