from budget_bot.bot.handlers.fallback import (
    STALE_BUTTON_TEXT,
    UNRECOGNIZED_TEXT,
    unmatched_callback,
    unmatched_message,
)
from tests.conftest import FakeCallback, FakeMessage


async def test_unmatched_callback_tells_the_user_the_button_is_stale():
    callback = FakeCallback(data="something-nothing-claims")

    await unmatched_callback(callback)

    assert callback.answers[-1] == (STALE_BUTTON_TEXT, True)


async def test_unmatched_message_points_to_add_or_the_menu():
    message = FakeMessage(text="кава 100")

    await unmatched_message(message)

    assert message.last_reply == UNRECOGNIZED_TEXT
