from budget_bot.bot.handlers.categories import (
    AddCategory,
    cb_start_add_category,
    cmd_categories,
    enter_category_name,
)
from budget_bot.services.categories import list_categories
from tests.conftest import FakeCallback, FakeMessage


async def test_categories_command_lists_defaults(session, member, category, state):
    message = FakeMessage(text="/categories")

    await cmd_categories(message, session=session, member=member, state=state)

    text = message.last_reply
    assert "Їжа" in text and "Інше" in text
    assert "Оренда житла" in text


async def test_add_category_dialog_saves_new_category(session, member, category, state):
    callback = FakeCallback()
    await cb_start_add_category(callback, state=state)
    assert await state.get_state() == AddCategory.name

    message = FakeMessage(text="Кава")
    await enter_category_name(message, state=state, session=session, member=member)

    names = [item.name for item in await list_categories(session, member.household_id)]
    assert "Кава" in names
    assert await state.get_state() is None
    assert "Кава" in message.last_reply


async def test_duplicate_is_rejected_with_explanation_and_state_kept(
    session, member, category, state
):
    await state.set_state(AddCategory.name)
    message = FakeMessage(text="їжа")

    await enter_category_name(message, state=state, session=session, member=member)

    assert "вже існує" in message.last_reply
    assert await state.get_state() == AddCategory.name
    assert len(await list_categories(session, member.household_id)) == 9


async def test_empty_name_is_rejected(session, member, category, state):
    await state.set_state(AddCategory.name)
    message = FakeMessage(text="   ")

    await enter_category_name(message, state=state, session=session, member=member)

    assert "порожньою" in message.last_reply
    assert await state.get_state() == AddCategory.name


async def test_duplicate_error_escapes_the_existing_category_name(session, member, state):
    await enter_category_name(
        FakeMessage(text="<b>Кава</b>"), state=state, session=session, member=member
    )
    await state.set_state(AddCategory.name)

    message = FakeMessage(text="<B>кава</B>")
    await enter_category_name(message, state=state, session=session, member=member)

    assert "<b>Кава</b>" not in message.last_reply
    assert "&lt;b&gt;Кава&lt;/b&gt;" in message.last_reply
