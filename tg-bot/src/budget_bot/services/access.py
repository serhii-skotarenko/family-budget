"""Household bootstrap and Telegram-user → Member resolution.

The MVP has exactly one household; it is created lazily on the first update
from a whitelisted user, together with the default category list.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Household, Member
from budget_bot.services.categories import ensure_default_categories


async def get_or_create_household(session: AsyncSession, name: str) -> Household:
    household = await session.scalar(select(Household).order_by(Household.id).limit(1))
    if household is not None:
        return household

    household = Household(name=name)
    session.add(household)
    await session.flush()
    await ensure_default_categories(session, household.id)
    return household


async def resolve_member(
    session: AsyncSession, *, telegram_id: int, display_name: str, household_name: str
) -> Member:
    household = await get_or_create_household(session, household_name)
    member = await session.scalar(select(Member).where(Member.telegram_id == telegram_id))

    if member is None:
        member = Member(
            household_id=household.id, telegram_id=telegram_id, display_name=display_name
        )
        session.add(member)
        await session.flush()
        return member

    if display_name and member.display_name != display_name:
        member.display_name = display_name
        await session.flush()
    return member


async def list_members(session: AsyncSession, household_id: int) -> list[Member]:
    result = await session.scalars(
        select(Member).where(Member.household_id == household_id).order_by(Member.id)
    )
    return list(result)
