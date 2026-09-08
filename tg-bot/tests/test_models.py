import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from budget_bot.clock import utcnow
from budget_bot.models import Category, Expense, Household, Member


async def test_expense_relationships_load_without_lazy_io(session):
    household = Household(name="Test")
    session.add(household)
    await session.flush()

    member = Member(household_id=household.id, telegram_id=111, display_name="Сергій")
    category = Category(household_id=household.id, name="Їжа", name_normalized="їжа")
    session.add_all([member, category])
    await session.flush()

    session.add(
        Expense(
            household_id=household.id,
            member_id=member.id,
            category_id=category.id,
            amount=250,
            description="кава",
            created_at=utcnow(),
        )
    )
    await session.commit()

    expense = (await session.execute(select(Expense))).scalar_one()
    assert expense.category.name == "Їжа"
    assert expense.author.display_name == "Сергій"
    assert expense.updated_by is None
    assert expense.amount == 250


async def test_category_name_is_unique_per_household(session):
    household = Household(name="Test")
    session.add(household)
    await session.flush()

    session.add(Category(household_id=household.id, name="Кава", name_normalized="кава"))
    await session.flush()
    session.add(Category(household_id=household.id, name="КАВА", name_normalized="кава"))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_telegram_id_is_unique(session):
    household = Household(name="Test")
    session.add(household)
    await session.flush()

    session.add(Member(household_id=household.id, telegram_id=111, display_name="A"))
    await session.flush()
    session.add(Member(household_id=household.id, telegram_id=111, display_name="B"))

    with pytest.raises(IntegrityError):
        await session.flush()


def test_utcnow_is_naive():
    assert utcnow().tzinfo is None
