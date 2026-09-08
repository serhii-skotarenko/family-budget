"""Aggregated spending reports for a period."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Category, Expense, Member
from budget_bot.periods import PeriodRange


@dataclass(frozen=True)
class CategoryTotal:
    name: str
    amount: int
    share: float  # percent of the period total, one decimal


@dataclass(frozen=True)
class MemberTotal:
    display_name: str
    amount: int


@dataclass(frozen=True)
class Report:
    period_label: str
    total: int
    by_category: list[CategoryTotal]
    by_member: list[MemberTotal]


async def build_report(session: AsyncSession, household_id: int, period: PeriodRange) -> Report:
    scope = (
        Expense.household_id == household_id,
        Expense.created_at >= period.start,
        Expense.created_at < period.end,
    )

    total = await session.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).where(*scope))
    if not total:
        return Report(period_label=period.label, total=0, by_category=[], by_member=[])

    category_rows = await session.execute(
        select(Category.name, func.sum(Expense.amount))
        .join(Category, Category.id == Expense.category_id)
        .where(*scope)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(Expense.amount).desc(), Category.name)
    )
    member_rows = await session.execute(
        select(Member.display_name, func.sum(Expense.amount))
        .join(Member, Member.id == Expense.member_id)
        .where(*scope)
        .group_by(Member.id, Member.display_name)
        .order_by(func.sum(Expense.amount).desc(), Member.display_name)
    )

    return Report(
        period_label=period.label,
        total=int(total),
        by_category=[
            CategoryTotal(name=name, amount=int(amount), share=round(amount * 100 / total, 1))
            for name, amount in category_rows.all()
        ],
        by_member=[
            MemberTotal(display_name=name, amount=int(amount)) for name, amount in member_rows.all()
        ],
    )
