from types import SimpleNamespace

from budget_bot.bot.replies import edit_or_answer
from tests.conftest import FakeMessage


class FakeInaccessibleMessage:
    """Stand-in for aiogram's ``InaccessibleMessage``: has ``answer()``, not ``edit_text()``.

    Telegram substitutes this for a callback's message once it is older than
    48 hours, so it is not an instance of ``aiogram.types.Message``.
    """

    def __init__(self) -> None:
        self.replies: list[tuple[str, dict]] = []

    async def answer(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return self


async def test_edit_or_answer_edits_a_real_message():
    message = FakeMessage()
    callback = SimpleNamespace(message=message)

    await edit_or_answer(callback, "Готово")

    assert message.last_edit == "Готово"
    assert message.replies == []


async def test_edit_or_answer_falls_back_to_answer_for_an_inaccessible_message():
    message = FakeInaccessibleMessage()
    callback = SimpleNamespace(message=message)

    await edit_or_answer(callback, "Готово")

    assert message.replies[-1][0] == "Готово"


async def test_edit_or_answer_does_nothing_when_there_is_no_message():
    callback = SimpleNamespace(message=None)

    await edit_or_answer(callback, "Готово")  # must not raise
