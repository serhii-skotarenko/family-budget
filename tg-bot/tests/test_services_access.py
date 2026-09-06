from sqlalchemy import func, select

from budget_bot.models import Category, Household, Member
from budget_bot.services.access import get_or_create_household, list_members, resolve_member


async def test_creates_household_with_default_categories_on_first_call(session):
    household = await get_or_create_household(session, "Сім'я")

    assert household.name == "Сім'я"
    count = await session.scalar(
        select(func.count()).select_from(Category).where(Category.household_id == household.id)
    )
    assert count == 9


async def test_reuses_the_single_household(session):
    first = await get_or_create_household(session, "Сім'я")
    second = await get_or_create_household(session, "Інша назва")

    assert first.id == second.id
    assert second.name == "Сім'я"
    assert await session.scalar(select(func.count()).select_from(Household)) == 1


async def test_both_members_join_the_same_household(session):
    one = await resolve_member(
        session, telegram_id=111, display_name="Сергій", household_name="Сім'я"
    )
    two = await resolve_member(session, telegram_id=222, display_name="Оля", household_name="Сім'я")

    assert one.household_id == two.household_id
    assert await session.scalar(select(func.count()).select_from(Member)) == 2


async def test_existing_member_is_reused_and_display_name_refreshed(session):
    created = await resolve_member(
        session, telegram_id=111, display_name="Сергій", household_name="Сім'я"
    )
    again = await resolve_member(
        session, telegram_id=111, display_name="Serhii", household_name="Сім'я"
    )

    assert again.id == created.id
    assert again.display_name == "Serhii"


async def test_list_members_is_ordered_by_id(session):
    await resolve_member(session, telegram_id=222, display_name="Оля", household_name="Сім'я")
    await resolve_member(session, telegram_id=111, display_name="Сергій", household_name="Сім'я")

    household = await get_or_create_household(session, "Сім'я")
    assert [m.display_name for m in await list_members(session, household.id)] == ["Оля", "Сергій"]
