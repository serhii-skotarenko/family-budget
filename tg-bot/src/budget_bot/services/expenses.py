"""Expense persistence and querying."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.clock import utcnow
from budget_bot.models import Expense
from budget_bot.periods import PeriodRange


@dataclass(frozen=True)
class ExpenseFilters:
    period: PeriodRange | None = None
    category_id: int | None = None
    member_id: int | None = None
    limit: int = 10


async def create_expense(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    category_id: int,
    amount: int,
    description: str | None = None,
    created_at: datetime | None = None,
) -> Expense:
    expense = Expense(
        household_id=household_id,
        member_id=member_id,
        category_id=category_id,
        amount=amount,
        description=description,
        created_at=created_at or utcnow(),
    )
    session.add(expense)
    await session.flush()
    await session.refresh(expense)
    return expense


async def get_expense(session: AsyncSession, household_id: int, expense_id: int) -> Expense | None:
    return await session.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.household_id == household_id)
    )


async def list_expenses(
    session: AsyncSession, household_id: int, filters: ExpenseFilters | None = None
) -> list[Expense]:
    filters = filters or ExpenseFilters()
    query = select(Expense).where(Expense.household_id == household_id)

    if filters.period is not None:
        query = query.where(
            Expense.created_at >= filters.period.start,
            Expense.created_at < filters.period.end,
        )
    if filters.category_id is not None:
        query = query.where(Expense.category_id == filters.category_id)
    if filters.member_id is not None:
        query = query.where(Expense.member_id == filters.member_id)

    query = query.order_by(Expense.created_at.desc(), Expense.id.desc()).limit(filters.limit)
    return list(await session.scalars(query))


class _Unset:
    """Sentinel type: distinguishes 'leave description alone' from 'clear it'."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNSET"


UNSET = _Unset()


async def update_expense(
    session: AsyncSession,
    expense: Expense,
    *,
    editor_id: int,
    amount: int | None = None,
    category_id: int | None = None,
    description: str | None | _Unset = UNSET,
) -> Expense:
    """Apply an edit. The author (member_id) is never reassigned."""
    if amount is not None:
        expense.amount = amount
    if category_id is not None:
        expense.category_id = category_id
    if not isinstance(description, _Unset):
        expense.description = description

    expense.updated_by_id = editor_id
    expense.updated_at = utcnow()

    await session.flush()
    await session.refresh(expense)
    return expense


async def delete_expense(session: AsyncSession, expense: Expense) -> None:
    await session.delete(expense)
    await session.flush()
