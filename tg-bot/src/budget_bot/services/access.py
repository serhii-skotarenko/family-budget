"""Household bootstrap and Telegram-user → Member resolution.

The MVP has exactly one household; it is created lazily on the first update
from a whitelisted user, together with the default category list.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Household, Member
from budget_bot.services.categories import ensure_default_categories

# The MVP has exactly one household. Its primary key is fixed so that two
# concurrent first-contacts (aiogram handles updates concurrently, each with
# its own session) racing SELECT-then-INSERT collide on the primary key
# instead of silently creating two household rows — Household has no other
# unique constraint to catch that.
SINGLETON_HOUSEHOLD_ID = 1


async def get_or_create_household(session: AsyncSession, name: str) -> Household:
    household = await session.scalar(select(Household).order_by(Household.id).limit(1))
    if household is not None:
        return household

    household = Household(id=SINGLETON_HOUSEHOLD_ID, name=name)
    try:
        # A SAVEPOINT, not a plain flush: on conflict, only this insert
        # unwinds, matching the pattern in services/categories.py.
        async with session.begin_nested():
            session.add(household)
            await session.flush()
    except IntegrityError:
        # A concurrent first-contact already created the singleton household
        # between our check above and this flush.
        household = await session.scalar(select(Household).order_by(Household.id).limit(1))
        if household is None:
            raise
        # Idempotent and savepoint-guarded; this conflict path almost never
        # runs, so the extra query is cheap insurance in case the winner's
        # own seeding lost its own race.
        await ensure_default_categories(session, household.id)
        return household

    await ensure_default_categories(session, household.id)
    return household


async def resolve_member(
    session: AsyncSession, *, telegram_id: int, display_name: str, household_name: str
) -> Member:
    household = await get_or_create_household(session, household_name)
    member = await session.scalar(select(Member).where(Member.telegram_id == telegram_id))

    if member is None:
        candidate = Member(
            household_id=household.id, telegram_id=telegram_id, display_name=display_name
        )
        try:
            # A SAVEPOINT, not a plain flush: on conflict, only this insert
            # unwinds, matching the pattern in services/categories.py.
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError:
            # A concurrent update for the same brand-new telegram_id (a
            # double-tap, or Telegram redelivering an update) already
            # created this member between our check above and this flush.
            member = await session.scalar(select(Member).where(Member.telegram_id == telegram_id))
            if member is None:
                raise
        else:
            return candidate

    if display_name and member.display_name != display_name:
        member.display_name = display_name
        await session.flush()
    return member


async def list_members(session: AsyncSession, household_id: int) -> list[Member]:
    result = await session.scalars(
        select(Member).where(Member.household_id == household_id).order_by(Member.id)
    )
    return list(result)
