"""Spending limits: append-only history, progress and forecast for the current period.

One-time expenses never count towards a limit (see the Phase 2 A spec).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.clock import utcnow
from budget_bot.models import Expense, Limit
from budget_bot.periods import Period, PeriodRange, period_range, to_kyiv

LIMIT_PERIODS = (Period.MONTH, Period.WEEK)
WARN_PERCENT = 80
GENERAL_LIMIT_NAME = "Загальний"


class LimitStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    OVER = "over"


def forecast(spent: int, days_elapsed: int, days_in_period: int) -> int:
    """Linear projection of the current pace onto the whole period."""
    return round(spent / days_elapsed * days_in_period)


def limit_status(percent: int, forecast_amount: int, amount: int) -> LimitStatus:
    if percent >= 100:
        return LimitStatus.OVER
    if percent >= WARN_PERCENT or forecast_amount > amount:
        return LimitStatus.WARN
    return LimitStatus.OK


def period_days(period: PeriodRange, now: datetime) -> tuple[int, int]:
    """(day_index, days_in_period) in Kyiv calendar days; today counts as elapsed."""
    first = to_kyiv(period.start).date()
    after_last = to_kyiv(period.end).date()
    today = to_kyiv(now).date()
    return (today - first).days + 1, (after_last - first).days


@dataclass(frozen=True)
class LimitProgress:
    limit_id: int
    period_type: Period
    category_id: int | None
    category_name: str | None
    amount: int
    spent: int
    period: PeriodRange
    day_index: int
    days_in_period: int

    @property
    def name(self) -> str:
        return self.category_name or GENERAL_LIMIT_NAME

    @property
    def percent(self) -> int:
        return self.spent * 100 // self.amount

    @property
    def remaining(self) -> int:
        return self.amount - self.spent

    @property
    def forecast(self) -> int:
        return forecast(self.spent, self.day_index, self.days_in_period)

    @property
    def status(self) -> LimitStatus:
        return limit_status(self.percent, self.forecast, self.amount)


async def _latest_rows(
    session: AsyncSession, household_id: int, now: datetime
) -> dict[tuple[str, int | None], Limit]:
    rows = await session.scalars(
        select(Limit)
        .where(Limit.household_id == household_id, Limit.effective_from <= now)
        .order_by(Limit.effective_from, Limit.id)
    )
    latest: dict[tuple[str, int | None], Limit] = {}
    for row in rows:
        latest[(row.period_type, row.category_id)] = row
    return latest


async def active_limits(session: AsyncSession, household_id: int, now: datetime) -> list[Limit]:
    latest = await _latest_rows(session, household_id, now)
    return [row for row in latest.values() if row.amount is not None]


async def get_active_limit(
    session: AsyncSession,
    household_id: int,
    period_type: Period,
    category_id: int | None,
    now: datetime,
) -> Limit | None:
    row = (await _latest_rows(session, household_id, now)).get((period_type.value, category_id))
    return row if row is not None and row.amount is not None else None


async def _append(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    period_type: Period,
    category_id: int | None,
    amount: int | None,
    now: datetime,
) -> Limit:
    row = Limit(
        household_id=household_id,
        category_id=category_id,
        period_type=period_type.value,
        amount=amount,
        effective_from=now,
        created_by_id=member_id,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def set_limit(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    period_type: Period,
    category_id: int | None,
    amount: int,
    now: datetime | None = None,
) -> Limit:
    return await _append(
        session,
        household_id=household_id,
        member_id=member_id,
        period_type=period_type,
        category_id=category_id,
        amount=amount,
        now=now or utcnow(),
    )


async def remove_limit(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    period_type: Period,
    category_id: int | None,
    now: datetime | None = None,
) -> bool:
    """Record the removal. Returns False when there was no active limit to remove."""
    now = now or utcnow()
    if await get_active_limit(session, household_id, period_type, category_id, now) is None:
        return False
    await _append(
        session,
        household_id=household_id,
        member_id=member_id,
        period_type=period_type,
        category_id=category_id,
        amount=None,
        now=now,
    )
    return True


async def limit_progress(
    session: AsyncSession, household_id: int, period_type: Period, now: datetime
) -> list[LimitProgress]:
    period = period_range(period_type, now)
    day_index, days_in_period = period_days(period, now)
    result = []
    for row in await active_limits(session, household_id, now):
        if row.period_type != period_type.value:
            continue
        query = select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.household_id == household_id,
            Expense.is_one_time.is_(False),
            Expense.created_at >= period.start,
            Expense.created_at < period.end,
        )
        if row.category_id is not None:
            query = query.where(Expense.category_id == row.category_id)
        result.append(
            LimitProgress(
                limit_id=row.id,
                period_type=period_type,
                category_id=row.category_id,
                category_name=row.category.name if row.category is not None else None,
                amount=row.amount,
                spent=int(await session.scalar(query)),
                period=period,
                day_index=day_index,
                days_in_period=days_in_period,
            )
        )
    result.sort(key=lambda p: (p.category_id is not None, (p.category_name or "").casefold()))
    return result


async def progress_for_expense(
    session: AsyncSession, expense: Expense, now: datetime
) -> list[LimitProgress]:
    """Limits this expense touches: its category's and the general ones, month then week."""
    if expense.is_one_time:
        return []
    result = []
    for period_type in LIMIT_PERIODS:
        result.extend(
            p
            for p in await limit_progress(session, expense.household_id, period_type, now)
            if p.category_id in (None, expense.category_id)
        )
    return result
