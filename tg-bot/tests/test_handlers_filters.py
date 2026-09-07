from datetime import datetime

from budget_bot.bot.callbacks import FilterCb
from budget_bot.bot.handlers.filters import (
    FilterFlow,
    choose_category,
    choose_member,
    choose_period,
    cmd_filter,
    enter_custom_range,
)
from budget_bot.clock import utcnow
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense
from tests.conftest import FakeCallback, FakeMessage


async def make(session, household, member, category, amount, when=None):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        created_at=when or utcnow(),
    )


async def run_flow(session, member, state, *, period="month", category="all", author="all"):
    callback = FakeCallback()
    await choose_period(
        callback,
        callback_data=FilterCb(step="period", value=period),
        state=state,
        session=session,
        member=member,
    )
    await choose_category(
        callback,
        callback_data=FilterCb(step="category", value=category),
        state=state,
        session=session,
        member=member,
    )
    await choose_member(
        callback,
        callback_data=FilterCb(step="member", value=author),
        state=state,
        session=session,
        member=member,
    )
    return callback


async def test_filter_starts_with_period_choice(state):
    message = FakeMessage(text="/filter")

    await cmd_filter(message, state=state)

    assert await state.get_state() == FilterFlow.choosing
    assert "період" in message.last_reply.lower()


async def test_filter_by_current_month_returns_matching_records(
    session, household, member, category, state
):
    await make(session, household, member, category, 500)
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = await run_flow(session, member, state)

    assert "500" in callback.message.last_reply
    assert await state.get_state() is None


async def test_filter_by_category_excludes_others(session, household, member, category, state):
    coffee = await add_category(session, household.id, "Кава")
    await make(session, household, member, category, 500)
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=coffee.id,
        amount=77,
        created_at=utcnow(),
    )
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = await run_flow(session, member, state, category=str(coffee.id))

    assert "77" in callback.message.last_reply
    assert "500" not in callback.message.last_reply


async def test_filter_by_author_excludes_partner(
    session, household, member, partner, category, state
):
    await make(session, household, member, category, 500)
    await make(session, household, partner, category, 77)
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = await run_flow(session, member, state, author=str(partner.id))

    assert "Оля" in callback.message.last_reply
    assert "500" not in callback.message.last_reply


async def test_empty_result_has_a_clear_message(session, member, category, state):
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = await run_flow(session, member, state)

    assert "Витрат за цей період не знайдено" in callback.message.last_reply


async def test_custom_range_is_validated_and_applied(session, household, member, category, state):
    await make(session, household, member, category, 500, when=datetime(2026, 9, 7, 9, 0))
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = FakeCallback()
    await choose_period(
        callback,
        callback_data=FilterCb(step="period", value="custom"),
        state=state,
        session=session,
        member=member,
    )
    assert await state.get_state() == FilterFlow.custom_range

    bad = FakeMessage(text="вчора")
    await enter_custom_range(bad, state=state, session=session, member=member)
    assert await state.get_state() == FilterFlow.custom_range
    assert "Формат" in bad.last_reply

    good = FakeMessage(text="01.09.2026-30.09.2026")
    await enter_custom_range(good, state=state, session=session, member=member)
    assert await state.get_state() == FilterFlow.choosing

    await choose_category(
        FakeCallback(),
        callback_data=FilterCb(step="category", value="all"),
        state=state,
        session=session,
        member=member,
    )
    result = FakeCallback()
    await choose_member(
        result,
        callback_data=FilterCb(step="member", value="all"),
        state=state,
        session=session,
        member=member,
    )

    assert "500" in result.message.last_reply
