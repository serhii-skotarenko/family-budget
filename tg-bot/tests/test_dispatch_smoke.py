"""One end-to-end check that update -> router -> handler wiring actually works.

Every other handler test calls the handler function directly, bypassing
routing, filters and middlewares entirely. That is exactly why a missing
message handler for a given FSM state, or a missing fallback router, was
invisible to 138 green tests. This builds the real Dispatcher with the real
routers and middlewares and feeds it a synthetic Update, so a router-wiring
mistake shows up as a failing assertion instead of a broken bot in
production.
"""

from datetime import datetime

import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import Chat, Message, Update, User

from budget_bot.bot.handlers import build_router
from budget_bot.bot.handlers.categories import AddCategory
from budget_bot.bot.middlewares import AccessMiddleware, DbSessionMiddleware
from budget_bot.db import create_engine, create_session_factory
from budget_bot.models import Base
from budget_bot.services.categories import list_categories

ALLOWED_ID = 111
FAKE_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


class RecordingSession(BaseSession):
    """Fake HTTP session: records outgoing Bot API calls instead of sending them."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self, bot: Bot, method: TelegramMethod[TelegramType], timeout: int | None = None
    ) -> TelegramType:
        self.requests.append(method)
        return True  # type: ignore[return-value]

    async def stream_content(
        self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True
    ):
        yield b""


@pytest_asyncio.fixture
async def wired_dispatcher(tmp_path):
    """A real Dispatcher, real routers and real middlewares over a real (temp-file) DB."""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'smoke.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)

    session = RecordingSession()
    bot = Bot(token=FAKE_TOKEN, session=session)

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    access = AccessMiddleware(frozenset({ALLOWED_ID}), "Сім'я")
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)
    dispatcher.include_router(build_router())

    try:
        yield dispatcher, bot, session, session_factory
    finally:
        await bot.session.close()
        await engine.dispose()


def _message_update(text: str, update_id: int = 1) -> Update:
    chat = Chat(id=ALLOWED_ID, type="private")
    user = User(id=ALLOWED_ID, is_bot=False, first_name="Сергій")
    message = Message(
        message_id=update_id, date=datetime.now(), chat=chat, from_user=user, text=text
    )
    return Update(update_id=update_id, message=message)


def _sent_texts(session: RecordingSession) -> list[str]:
    return [request.text for request in session.requests if isinstance(request, SendMessage)]


async def test_updates_are_routed_to_the_right_handler_through_the_real_stack(wired_dispatcher):
    """One dispatcher, one build_router() call: its routers are module-level
    singletons that can only be attached to a single parent router, so a
    second build_router() call in a second test would raise. Both cases
    live in one test for that reason.
    """
    dispatcher, bot, session, session_factory = wired_dispatcher

    # Case 1: a real command reaches its real handler through the real
    # router stack and middlewares (whitelist, DB session, FSM).
    await dispatcher.feed_update(bot, _message_update("/start", update_id=1))
    texts = _sent_texts(session)
    assert texts, "expected /start to trigger a reply"
    assert "бот сімейного бюджету" in texts[-1]

    # Case 2: Phase-2 free-text syntax ("кава 100") — no command, no active
    # FSM state, no reply-keyboard button — matches nothing but the
    # catch-all fallback router included last in build_router().
    await dispatcher.feed_update(bot, _message_update("кава 100", update_id=2))
    texts = _sent_texts(session)
    assert "Не зрозумів" in texts[-1]

    # Case 3: a slash command typed while an FSM dialog is waiting for text
    # must run the command, not be swallowed as the dialog's input. Found in
    # live testing: typing /report at the "name your category" prompt created
    # a category literally named "/report". Router order decided the outcome —
    # categories.router is included before reports.router, so its state
    # handler claimed the update first.
    state = FSMContext(
        storage=dispatcher.fsm.storage,
        key=StorageKey(bot_id=bot.id, chat_id=ALLOWED_ID, user_id=ALLOWED_ID),
    )
    await state.set_state(AddCategory.name)
    await dispatcher.feed_update(bot, _message_update("/report", update_id=3))

    texts = _sent_texts(session)
    assert (
        "Оберіть період звіту" in texts[-1]
    ), f"/report was swallowed by the category dialog instead of running; got: {texts[-1]!r}"
    async with session_factory() as check:
        names = [c.name for c in await list_categories(check, 1)]
    assert "/report" not in names, f"a junk category was created: {names}"

    # ...and running a command must end the dialog it interrupted. Otherwise
    # the state stays armed invisibly: the user sees the report prompt, thinks
    # they left the category dialog, and their next ordinary word is silently
    # stored as a category name.
    assert (
        await state.get_state() is None
    ), f"dialog state survived the command: {await state.get_state()}"
    await dispatcher.feed_update(bot, _message_update("Кава", update_id=4))
    texts = _sent_texts(session)
    assert "Не зрозумів" in texts[-1], f"plain text was still captured: {texts[-1]!r}"
    async with session_factory() as check:
        names = [c.name for c in await list_categories(check, 1)]
    assert "Кава" not in names, f"plain text became a category: {names}"
