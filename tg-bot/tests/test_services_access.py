from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Category, Household, Member
from budget_bot.services.access import (
    SINGLETON_HOUSEHOLD_ID,
    get_or_create_household,
    list_members,
    resolve_member,
)


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


async def test_get_or_create_household_survives_concurrent_creation(session, monkeypatch):
    """Two concurrent first-contacts (both users pressing Start around the
    same moment on a fresh database) race SELECT-then-INSERT with no unique
    constraint but the primary key to catch it. Force the real conflict by
    making the pre-check miss the row a concurrent transaction already
    committed with the singleton id, so a genuine IntegrityError is
    exercised rather than a mocked one."""
    winner = Household(id=SINGLETON_HOUSEHOLD_ID, name="Переможець")
    session.add(winner)
    await session.commit()
    # A real concurrent transaction would use its own session with its own
    # identity map. This test reuses one session for both "transactions", so
    # expunge the winner to avoid a same-session identity-map conflict when
    # the code under test adds a second Household with the same primary key.
    session.expunge(winner)

    real_scalar = AsyncSession.scalar
    call_count = 0

    async def racy_scalar(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate the pre-check missing the row a concurrent
            # transaction just committed.
            return None
        return await real_scalar(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "scalar", racy_scalar)

    household = await get_or_create_household(session, "Інша назва")

    monkeypatch.undo()
    assert household.id == SINGLETON_HOUSEHOLD_ID
    assert household.name == "Переможець"
    assert await session.scalar(select(func.count()).select_from(Household)) == 1


async def test_resolve_member_survives_concurrent_creation(session, household, monkeypatch):
    """Two concurrent resolve_member calls for the same brand-new
    telegram_id (a double-tap, or Telegram redelivering an update) race
    SELECT-then-INSERT against the unique telegram_id constraint. Force the
    real conflict by making the member pre-check miss the row a concurrent
    transaction already committed, so a genuine IntegrityError is
    exercised rather than a mocked one."""
    winner = Member(household_id=household.id, telegram_id=111, display_name="Сергій")
    session.add(winner)
    await session.commit()

    real_scalar = AsyncSession.scalar
    call_count = 0

    async def racy_scalar(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # Simulate the member pre-check (the second session.scalar call,
            # after get_or_create_household's own lookup) missing the row a
            # concurrent transaction just committed.
            return None
        return await real_scalar(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "scalar", racy_scalar)

    member = await resolve_member(
        session, telegram_id=111, display_name="Serhii", household_name=household.name
    )

    monkeypatch.undo()
    assert member.telegram_id == 111
    assert await session.scalar(select(func.count()).select_from(Member)) == 1
