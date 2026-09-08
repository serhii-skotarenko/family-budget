from datetime import datetime

from aiogram.types import Chat, ErrorEvent, Message, Update, User

from budget_bot.__main__ import handle_error


class SpyBot:
    """Minimal stand-in for aiogram Bot: records send_message calls."""

    def __init__(self, raise_on_send: Exception | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self._raise_on_send = raise_on_send

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        if self._raise_on_send is not None:
            raise self._raise_on_send
        self.sent.append((chat_id, text))


def make_message_update(update_id: int = 1, chat_id: int = 555) -> Update:
    chat = Chat(id=chat_id, type="private")
    user = User(id=chat_id, is_bot=False, first_name="Тест")
    message = Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text="/add")
    return Update(update_id=update_id, message=message)


async def test_handle_error_replies_in_the_originating_chat():
    bot = SpyBot()
    event = ErrorEvent(update=make_message_update(chat_id=555), exception=RuntimeError("boom"))

    await handle_error(event, bot=bot)

    assert bot.sent
    chat_id, text = bot.sent[-1]
    assert chat_id == 555
    assert "помилка" in text.lower()


async def test_handle_error_never_raises_even_if_the_apology_fails_to_send():
    bot = SpyBot(raise_on_send=RuntimeError("network down"))
    event = ErrorEvent(update=make_message_update(), exception=RuntimeError("boom"))

    await handle_error(event, bot=bot)  # must not raise


async def test_handle_error_without_a_resolvable_chat_does_nothing():
    bot = SpyBot()
    update = Update(update_id=2)  # no message, no callback_query
    event = ErrorEvent(update=update, exception=RuntimeError("boom"))

    await handle_error(event, bot=bot)

    assert bot.sent == []
