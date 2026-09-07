from budget_bot.bot.handlers import build_router
from budget_bot.bot.handlers.common import cb_cancel, cmd_cancel, cmd_start
from budget_bot.bot.keyboards import BTN_ADD, main_menu
from tests.conftest import FakeCallback, FakeMessage


async def test_start_greets_by_display_name_and_lists_commands(member):
    message = FakeMessage(text="/start")

    await cmd_start(message, member=member)

    text, kwargs = message.replies[-1]
    assert "Сергій" in text
    assert "/add" in text and "/report" in text and "/cancel" in text
    assert kwargs["reply_markup"] is not None


async def test_start_escapes_html_in_the_display_name(member):
    member.display_name = "<script>hack</script>"
    message = FakeMessage(text="/start")

    await cmd_start(message, member=member)

    text = message.last_reply
    assert "&lt;script&gt;hack&lt;/script&gt;" in text
    assert "<script>hack</script>" not in text


async def test_cancel_without_active_dialog(state):
    message = FakeMessage(text="/cancel")

    await cmd_cancel(message, state=state)

    assert "Немає активного діалогу" in message.last_reply


async def test_cancel_clears_state(state):
    await state.update_data(amount=100)
    await state.set_state("SomeState:step")
    message = FakeMessage(text="/cancel")

    await cmd_cancel(message, state=state)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert "Скасовано" in message.last_reply


async def test_cancel_callback_clears_state(state):
    await state.set_state("SomeState:step")
    callback = FakeCallback()

    await cb_cancel(callback, state=state)

    assert await state.get_state() is None
    assert "Скасовано" in callback.message.last_edit


def test_main_menu_has_add_button():
    labels = [button.text for row in main_menu().keyboard for button in row]
    assert BTN_ADD in labels


def test_build_router_returns_router():
    assert build_router().name == "root"
