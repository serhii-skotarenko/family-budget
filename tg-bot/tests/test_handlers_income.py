from budget_bot.bot.handlers.income import SetIncome, cmd_setincome, enter_income
from budget_bot.clock import utcnow
from budget_bot.services.income import income_at, set_income
from tests.conftest import FakeMessage


async def test_first_income(session, member, state):
    prompt = FakeMessage(text="/setincome")
    await cmd_setincome(prompt, state=state, session=session, member=member)

    assert await state.get_state() == SetIncome.amount
    assert "зараз" not in prompt.last_reply

    reply = FakeMessage(text="300 000")
    await enter_income(reply, state=state, session=session, member=member)

    assert await state.get_state() is None
    assert await income_at(session, member.household_id, utcnow()) == 300000
    assert reply.last_reply.startswith("✅ Дохід: <b>300 000 ₴</b>/міс, діє з ")


async def test_changing_income_shows_the_previous_one(session, member, state):
    await set_income(session, household_id=member.household_id, member_id=member.id, amount=300000)
    prompt = FakeMessage(text="/setincome")
    await cmd_setincome(prompt, state=state, session=session, member=member)

    assert "(зараз: 300 000 ₴)" in prompt.last_reply

    reply = FakeMessage(text="312000")
    await enter_income(reply, state=state, session=session, member=member)

    assert "/міс (було 300 000 ₴), діє з " in reply.last_reply
    assert await income_at(session, member.household_id, utcnow()) == 312000


async def test_invalid_amount_keeps_the_step(session, member, state):
    await state.set_state(SetIncome.amount)
    message = FakeMessage(text="0")

    await enter_income(message, state=state, session=session, member=member)

    assert await state.get_state() == SetIncome.amount
    assert "більшою за нуль" in message.last_reply
    assert await income_at(session, member.household_id, utcnow()) is None
