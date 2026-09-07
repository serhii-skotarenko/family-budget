from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.db import create_engine, create_session_factory
from budget_bot.models import Base, Category, Household, Member
from budget_bot.services.categories import ensure_default_categories, list_categories


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """In-memory SQLite session with the full schema created.

    The aiosqlite dialect uses a StaticPool for ``:memory:``, so every
    checkout shares one connection and the schema survives between calls.
    """
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest_asyncio.fixture
async def household(session) -> Household:
    item = Household(name="Тест")
    session.add(item)
    await session.flush()
    return item


@pytest_asyncio.fixture
async def member(session, household) -> Member:
    item = Member(household_id=household.id, telegram_id=111, display_name="Сергій")
    session.add(item)
    await session.flush()
    return item


@pytest_asyncio.fixture
async def partner(session, household) -> Member:
    item = Member(household_id=household.id, telegram_id=222, display_name="Оля")
    session.add(item)
    await session.flush()
    return item


@pytest_asyncio.fixture
async def category(session, household) -> Category:
    await ensure_default_categories(session, household.id)
    return (await list_categories(session, household.id))[0]  # Їжа


class FakeMessage:
    """Minimal stand-in for aiogram Message: records what the bot sent back."""

    def __init__(self, text: str = "", user_id: int = 111, first_name: str = "Сергій") -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id, first_name=first_name)
        self.replies: list[tuple[str, dict]] = []
        self.edits: list[tuple[str, dict]] = []

    async def answer(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return self

    async def edit_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))
        return self

    @property
    def last_reply(self) -> str:
        return self.replies[-1][0]

    @property
    def last_edit(self) -> str:
        return self.edits[-1][0]


class FakeCallback:
    """Minimal stand-in for aiogram CallbackQuery."""

    def __init__(self, data: str = "", user_id: int = 111, first_name: str = "Сергій") -> None:
        self.data = data
        self.message = FakeMessage(user_id=user_id, first_name=first_name)
        self.from_user = SimpleNamespace(id=user_id, first_name=first_name)
        self.answers: list[tuple[str, bool]] = []

    async def answer(self, text: str = "", show_alert: bool = False, **kwargs) -> None:
        self.answers.append((text, show_alert))


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=111))
