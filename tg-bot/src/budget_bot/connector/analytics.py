"""Read-only spending analytics behind the Claude connector tools.

Each function takes an AsyncSession plus already-validated arguments and
returns a model from schemas.py. Anything grouped by Kyiv calendar day is
grouped in Python: SQLite knows nothing about Europe/Kyiv or its DST switches.
"""

from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.connector.inputs import DateRange, InvalidRequest
from budget_bot.connector.schemas import (
    BudgetOverview,
    CategoryInfo,
    CategorySpending,
    MemberSpending,
    SpendingSummary,
)
from budget_bot.models import Category, Expense, Member
from budget_bot.periods import kyiv_day_range, to_kyiv
from budget_bot.services.access import SINGLETON_HOUSEHOLD_ID, list_members
from budget_bot.services.categories import list_categories, normalize_category_name

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
    )


async def summarize_spending(
    session: AsyncSession,
    date_range: DateRange,
    *,
    category: Category | None,
    member: Member | None,
) -> SpendingSummary:
    conditions = _conditions(date_range, category, member)
    amount = func.sum(Expense.amount)
    category_rows = (
        await session.execute(
            select(Category.name, amount, func.count(Expense.id))
            .join(Category, Category.id == Expense.category_id)
            .where(*conditions)
            .group_by(Category.id, Category.name)
            .order_by(amount.desc(), Category.name)
        )
    ).all()
    member_rows = (
        await session.execute(
            select(Member.display_name, amount, func.count(Expense.id))
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
        total=total,
        expense_count=sum(row[2] for row in category_rows),
        by_category=[
            CategorySpending(
                name=name, amount=value, share_percent=round(value * 100 / total, 1), count=n
            )
            for name, value, n in category_rows
        ],
        by_member=[
            MemberSpending(name=name, amount=value, count=n) for name, value, n in member_rows
        ],
    )


def _conditions(
    date_range: DateRange, category: Category | None, member: Member | None
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
    return conditions
