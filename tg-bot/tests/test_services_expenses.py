from datetime import datetime

from budget_bot.clock import utcnow
from budget_bot.periods import Period, period_range
from budget_bot.services.expenses import ExpenseFilters, create_expense, get_expense, list_expenses

NOW = datetime(2026, 9, 9, 9, 0)  # Wednesday 12:00 Kyiv


async def add(session, household, member, category, *, amount, when, description=None):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        description=description,
        created_at=when,
    )


async def test_create_persists_all_fields(session, household, member, category):
    expense = await add(
        session, household, member, category, amount=250, when=NOW, description="кава"
    )

    assert expense.id is not None
    assert expense.amount == 250
    assert expense.description == "кава"
    assert expense.created_at == NOW
    assert expense.member_id == member.id
    assert expense.updated_at is None


async def test_create_defaults_created_at_to_now(session, household, member, category):
    before = utcnow()
    expense = await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=100,
    )
    assert expense.created_at >= before.replace(microsecond=0)
    assert expense.created_at.tzinfo is None


async def test_list_returns_newest_first_and_respects_limit(session, household, member, category):
    await add(session, household, member, category, amount=1, when=datetime(2026, 9, 1, 9, 0))
    await add(session, household, member, category, amount=2, when=datetime(2026, 9, 2, 9, 0))
    await add(session, household, member, category, amount=3, when=datetime(2026, 9, 3, 9, 0))

    result = await list_expenses(session, household.id, ExpenseFilters(limit=2))
    assert [e.amount for e in result] == [3, 2]


async def test_period_filter_is_half_open(session, household, member, category):
    week = period_range(Period.WEEK, NOW)  # 07.09–13.09 Kyiv
    await add(session, household, member, category, amount=10, when=week.start)
    await add(session, household, member, category, amount=20, when=week.end)

    result = await list_expenses(session, household.id, ExpenseFilters(period=week))
    assert [e.amount for e in result] == [10]


async def test_filters_by_category(session, household, member, category):
    from budget_bot.services.categories import add_category

    other = await add_category(session, household.id, "Кава")
    await add(session, household, member, category, amount=10, when=NOW)
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=other.id,
        amount=20,
        created_at=NOW,
    )

    result = await list_expenses(session, household.id, ExpenseFilters(category_id=other.id))
    assert [e.amount for e in result] == [20]


async def test_filters_by_author(session, household, member, partner, category):
    await add(session, household, member, category, amount=10, when=NOW)
    await add(session, household, partner, category, amount=20, when=NOW)

    result = await list_expenses(session, household.id, ExpenseFilters(member_id=partner.id))
    assert [e.amount for e in result] == [20]
    assert result[0].author.display_name == "Оля"


async def test_empty_result_is_an_empty_list(session, household, member, category):
    result = await list_expenses(session, household.id, ExpenseFilters(member_id=member.id))
    assert result == []


async def test_get_expense_is_scoped_to_household(session, household, member, category):
    expense = await add(session, household, member, category, amount=10, when=NOW)

    assert await get_expense(session, household.id, expense.id) is not None
    assert await get_expense(session, household.id + 1, expense.id) is None
