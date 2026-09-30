"""Read-only spending analytics behind the Claude connector tools.

Each function takes an AsyncSession plus already-validated arguments and
returns a model from schemas.py. Anything grouped by Kyiv calendar day is
grouped in Python: SQLite knows nothing about Europe/Kyiv or its DST switches.
"""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.connector.inputs import MAX_TREND_BUCKETS, DateRange, InvalidRequest
from budget_bot.connector.schemas import (
    BreakdownItem,
    BudgetOverview,
    CashflowMonth,
    CashflowReport,
    CategoryInfo,
    CategorySpending,
    ExpenseItem,
    ExpensePage,
    Granularity,
    LimitItem,
    LimitPeriodProgress,
    LimitProgressReport,
    MemberSpending,
    OneTimeFilter,
    SortOrder,
    SpendingSummary,
    SpendingTrend,
    SplitBy,
    TrendBucket,
)
from budget_bot.models import Category, Expense, Member
from budget_bot.periods import kyiv_day_range, period_range, to_kyiv
from budget_bot.services.access import SINGLETON_HOUSEHOLD_ID, list_members
from budget_bot.services.categories import list_categories, normalize_category_name
from budget_bot.services.income import (
    income_at,
    month_cashflow,
    month_first,
    month_range,
    next_month,
)
from budget_bot.services.limits import LIMIT_PERIODS, limit_progress, period_days

HOUSEHOLD_ID = SINGLETON_HOUSEHOLD_ID
TIMEZONE = "Europe/Kyiv"
CURRENCY = "UAH"


async def find_category(session: AsyncSession, name: str | None) -> Category | None:
    """Resolve a category by name, ignoring case and extra spaces; None means no filter."""
    if name is None:
        return None
    categories = await list_categories(session, HOUSEHOLD_ID)
    wanted = normalize_category_name(name)
    for category in categories:
        if category.name_normalized == wanted:
            return category
    known = ", ".join(category.name for category in categories) or "none yet"
    raise InvalidRequest(f"Unknown category {name!r}. Known categories: {known}")


async def find_member(session: AsyncSession, name: str | None) -> Member | None:
    """Resolve a member by display name, ignoring case and extra spaces; None means no filter."""
    if name is None:
        return None
    members = await list_members(session, HOUSEHOLD_ID)
    # Same folding as category names: SQLite's LOWER() would not fold Cyrillic.
    wanted = normalize_category_name(name)
    matches = [m for m in members if normalize_category_name(m.display_name) == wanted]
    known = ", ".join(member.display_name for member in members) or "none yet"
    if not matches:
        raise InvalidRequest(f"Unknown member {name!r}. Known members: {known}")
    if len(matches) > 1:
        raise InvalidRequest(f"Member name {name!r} is ambiguous. Known members: {known}")
    return matches[0]


async def budget_overview(session: AsyncSession, now_utc: datetime) -> BudgetOverview:
    members = await list_members(session, HOUSEHOLD_ID)
    categories = await list_categories(session, HOUSEHOLD_ID)
    count, first, last = (
        await session.execute(
            select(
                func.count(Expense.id), func.min(Expense.created_at), func.max(Expense.created_at)
            ).where(Expense.household_id == HOUSEHOLD_ID)
        )
    ).one()
    return BudgetOverview(
        today=to_kyiv(now_utc).date(),
        timezone=TIMEZONE,
        currency=CURRENCY,
        members=[member.display_name for member in members],
        categories=[CategoryInfo(name=c.name, is_custom=c.is_custom) for c in categories],
        first_expense_date=to_kyiv(first).date() if first is not None else None,
        last_expense_date=to_kyiv(last).date() if last is not None else None,
        expense_count=count,
        current_monthly_income=await income_at(session, HOUSEHOLD_ID, now_utc),
    )


async def summarize_spending(
    session: AsyncSession,
    date_range: DateRange,
    *,
    category: Category | None,
    member: Member | None,
    one_time: OneTimeFilter = "all",
) -> SpendingSummary:
    conditions = _conditions(date_range, category, member, one_time)
    amount = func.sum(Expense.amount)
    category_rows = (
        await session.execute(
            select(Category.name, amount, func.count(Expense.id), ONE_TIME_SUM)
            .join(Category, Category.id == Expense.category_id)
            .where(*conditions)
            .group_by(Category.id, Category.name)
            .order_by(amount.desc(), Category.name)
        )
    ).all()
    member_rows = (
        await session.execute(
            select(Member.display_name, amount, func.count(Expense.id), ONE_TIME_SUM)
            .join(Member, Member.id == Expense.member_id)
            .where(*conditions)
            .group_by(Member.id, Member.display_name)
            .order_by(amount.desc(), Member.display_name)
        )
    ).all()

    total = sum(row[1] for row in category_rows)
    return SpendingSummary(
        start_date=date_range.first,
        end_date=date_range.last,
        category=category.name if category is not None else None,
        member=member.display_name if member is not None else None,
        one_time=one_time,
        total=total,
        one_time_amount=sum(row[3] for row in category_rows),
        expense_count=sum(row[2] for row in category_rows),
        by_category=[
            CategorySpending(
                name=name,
                amount=value,
                share_percent=round(value * 100 / total, 1),
                count=n,
                one_time_amount=part,
            )
            for name, value, n, part in category_rows
        ],
        by_member=[
            MemberSpending(name=name, amount=value, count=n, one_time_amount=part)
            for name, value, n, part in member_rows
        ],
    )


def _conditions(
    date_range: DateRange,
    category: Category | None,
    member: Member | None,
    one_time: OneTimeFilter = "all",
) -> list[ColumnElement[bool]]:
    period = kyiv_day_range(date_range.first, date_range.last)
    conditions = [
        Expense.household_id == HOUSEHOLD_ID,
        Expense.created_at >= period.start,
        Expense.created_at < period.end,
    ]
    if category is not None:
        conditions.append(Expense.category_id == category.id)
    if member is not None:
        conditions.append(Expense.member_id == member.id)
    if one_time == "exclude":
        conditions.append(Expense.is_one_time.is_(False))
    elif one_time == "only":
        conditions.append(Expense.is_one_time.is_(True))
    return conditions


# Sum of the one-time part, usable next to func.sum(Expense.amount) in any grouping.
ONE_TIME_SUM = func.sum(case((Expense.is_one_time, Expense.amount), else_=0))


@dataclass(frozen=True)
class BucketSpan:
    first: date
    last: date
    partial: bool


def trend_buckets(date_range: DateRange, granularity: Granularity) -> list[BucketSpan]:
    """Weeks (Monday–Sunday) or calendar months covering the range, clipped to it."""
    count = _bucket_count(date_range, granularity)
    if count > MAX_TREND_BUCKETS:
        hint = (
            'use granularity="month" or a shorter date range'
            if granularity == "week"
            else "use a shorter date range"
        )
        raise InvalidRequest(
            f"{date_range.first.isoformat()}..{date_range.last.isoformat()} gives {count} "
            f"{granularity} buckets (max {MAX_TREND_BUCKETS}); {hint}"
        )

    spans = []
    start = _bucket_start(date_range.first, granularity)
    while start <= date_range.last:
        end = _bucket_end(start, granularity)
        first = max(start, date_range.first)
        last = min(end, date_range.last)
        spans.append(BucketSpan(first=first, last=last, partial=(first, last) != (start, end)))
        start = end + timedelta(days=1)
    return spans


async def spending_trend(
    session: AsyncSession,
    date_range: DateRange,
    *,
    granularity: Granularity,
    split_by: SplitBy,
    category: Category | None,
    member: Member | None,
    one_time: OneTimeFilter = "all",
) -> SpendingTrend:
    spans = trend_buckets(date_range, granularity)
    rows = (
        await session.execute(
            select(
                Expense.created_at,
                Expense.amount,
                Expense.is_one_time,
                Category.name,
                Member.display_name,
            )
            .join(Category, Category.id == Expense.category_id)
            .join(Member, Member.id == Expense.member_id)
            .where(*_conditions(date_range, category, member, one_time))
        )
    ).all()

    starts = [span.first for span in spans]
    totals = [0] * len(spans)
    counts = [0] * len(spans)
    one_time_parts = [0] * len(spans)
    # name -> [amount, count, one-time amount]
    groups: list[defaultdict[str, list[int]]] = [defaultdict(lambda: [0, 0, 0]) for _ in spans]
    for created_at, amount, is_one_time, category_name, member_name in rows:
        index = bisect_right(starts, to_kyiv(created_at).date()) - 1
        part = amount if is_one_time else 0
        totals[index] += amount
        counts[index] += 1
        one_time_parts[index] += part
        if split_by != "none":
            entry = groups[index][category_name if split_by == "category" else member_name]
            entry[0] += amount
            entry[1] += 1
            entry[2] += part

    return SpendingTrend(
        start_date=date_range.first,
        end_date=date_range.last,
        granularity=granularity,
        split_by=split_by,
        category=category.name if category is not None else None,
        member=member.display_name if member is not None else None,
        one_time=one_time,
        buckets=[
            TrendBucket(
                start_date=span.first,
                end_date=span.last,
                partial=span.partial,
                total=totals[index],
                count=counts[index],
                one_time_amount=one_time_parts[index],
                breakdown=None if split_by == "none" else _breakdown(groups[index]),
            )
            for index, span in enumerate(spans)
        ],
    )


def _bucket_start(day: date, granularity: Granularity) -> date:
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def _bucket_end(start: date, granularity: Granularity) -> date:
    if granularity == "week":
        return start + timedelta(days=6)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def _bucket_count(date_range: DateRange, granularity: Granularity) -> int:
    if granularity == "week":
        first_week = _bucket_start(date_range.first, "week")
        last_week = _bucket_start(date_range.last, "week")
        return (last_week - first_week).days // 7 + 1
    first, last = date_range.first, date_range.last
    return (last.year - first.year) * 12 + last.month - first.month + 1


def _breakdown(group: dict[str, list[int]]) -> list[BreakdownItem]:
    ordered = sorted(group.items(), key=lambda item: (-item[1][0], item[0]))
    return [
        BreakdownItem(name=name, amount=amount, count=n, one_time_amount=part)
        for name, (amount, n, part) in ordered
    ]


_SORTS = {
    "newest": (lambda row: (row.created_at, row.id), True),
    "oldest": (lambda row: (row.created_at, row.id), False),
    "largest": (lambda row: (row.amount, row.created_at, row.id), True),
}


async def list_expenses(
    session: AsyncSession,
    date_range: DateRange,
    *,
    category: Category | None,
    member: Member | None,
    search: str | None,
    min_amount: int | None,
    sort: SortOrder,
    limit: int,
    offset: int,
    one_time: OneTimeFilter = "all",
) -> ExpensePage:
    query = (
        select(
            Expense.id,
            Expense.created_at,
            Expense.amount,
            Expense.description,
            Expense.is_one_time,
            Category.name.label("category"),
            Member.display_name.label("member"),
        )
        .join(Category, Category.id == Expense.category_id)
        .join(Member, Member.id == Expense.member_id)
        .where(*_conditions(date_range, category, member, one_time))
    )
    if min_amount is not None:
        query = query.where(Expense.amount >= min_amount)
    rows = list((await session.execute(query)).all())

    needle = (search or "").strip().casefold()
    if needle:
        # In Python, not SQL: SQLite's LOWER() only folds ASCII letters.
        rows = [row for row in rows if row.description and needle in row.description.casefold()]

    key, reverse = _SORTS[sort]
    rows.sort(key=key, reverse=reverse)
    page = rows[offset : offset + limit]
    return ExpensePage(
        items=[
            ExpenseItem(
                id=row.id,
                datetime=to_kyiv(row.created_at),
                amount=row.amount,
                category=row.category,
                member=row.member,
                description=row.description,
                is_one_time=row.is_one_time,
            )
            for row in page
        ],
        total_count=len(rows),
        offset=offset,
        next_offset=offset + limit if offset + limit < len(rows) else None,
    )


async def limit_progress_report(
    session: AsyncSession, day: date, *, now_utc: datetime
) -> LimitProgressReport:
    """Limit progress for the month and the week containing ``day``.

    Figures come from services.limits, as in the bot's /limits. A past period
    is evaluated at its last moment, so it uses the limits in force at its end
    and its forecast equals what was spent.
    """
    today = to_kyiv(now_utc).date()
    if day > today:
        raise InvalidRequest(
            f"date {day.isoformat()} is in the future; today in Kyiv is {today.isoformat()}"
        )

    anchor = kyiv_day_range(day, day).start
    periods = []
    for period_type in LIMIT_PERIODS:
        bounds = period_range(period_type, anchor)
        as_of = min(now_utc, bounds.end - timedelta(microseconds=1))
        day_index, days_in_period = period_days(bounds, as_of)
        progress = await limit_progress(session, HOUSEHOLD_ID, period_type, as_of)
        periods.append(
            LimitPeriodProgress(
                period_type=period_type.value,
                start_date=to_kyiv(bounds.start).date(),
                end_date=to_kyiv(bounds.end).date() - timedelta(days=1),
                day_index=day_index,
                days_in_period=days_in_period,
                complete=now_utc >= bounds.end,
                limits=[
                    LimitItem(
                        category=item.category_name,
                        amount=item.amount,
                        spent=item.spent,
                        percent=item.percent,
                        remaining=item.remaining,
                        forecast=item.forecast,
                        status=item.status.value,
                    )
                    for item in progress
                ],
            )
        )
    return LimitProgressReport(date=day, periods=periods)


async def cashflow_report(
    session: AsyncSession, date_range: DateRange, *, now_utc: datetime
) -> CashflowReport:
    """Income and free cashflow per whole calendar month overlapping the range."""
    first = month_first(date_range.first)
    last = min(month_first(date_range.last), month_first(to_kyiv(now_utc).date()))
    count = (last.year - first.year) * 12 + last.month - first.month + 1
    if count > MAX_TREND_BUCKETS:
        raise InvalidRequest(
            f"{date_range.first.isoformat()}..{date_range.last.isoformat()} gives {count} "
            f"months (max {MAX_TREND_BUCKETS}); use a shorter date range"
        )

    months = []
    month = first
    while month <= last:
        item = await month_cashflow(session, HOUSEHOLD_ID, month, now_utc)
        bounds = month_range(month)
        months.append(
            CashflowMonth(
                month_start=month,
                month_end=to_kyiv(bounds.end).date() - timedelta(days=1),
                income=item.income,
                spent=item.spent,
                one_time_amount=item.one_time,
                free_cashflow=item.free,
                complete=item.complete,
            )
        )
        month = next_month(month)
    return CashflowReport(start_date=date_range.first, end_date=date_range.last, months=months)
