from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.config import Settings
from budget_bot.db import create_engine, create_readonly_engine, create_session_factory
from budget_bot.models import Base, Category, Household, Member
from budget_bot.periods import KYIV
from budget_bot.services.access import SINGLETON_HOUSEHOLD_ID
from budget_bot.services.categories import ensure_default_categories, list_categories
from budget_bot.services.expenses import create_expense


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


class FakeMessage(Message):
    """Minimal stand-in for aiogram Message: records what the bot sent back.

    Subclassing the real ``Message`` (via ``model_construct``, mirroring
    ``FakeCallback`` below) keeps ``isinstance(message, Message)`` — the
    check ``budget_bot.bot.replies.edit_or_answer`` uses to choose
    ``edit_text`` over ``answer`` — true under test. A plain duck-typed
    double would always fail that check and silently exercise the wrong
    branch.
    """

    def __init__(
        self,
        text: str = "",
        user_id: int = 111,
        first_name: str = "Сергій",
        chat_type: str = "private",
    ) -> None:
        user = User(id=user_id, is_bot=False, first_name=first_name)
        chat = Chat(id=user_id, type=chat_type)
        built = Message.model_construct(
            message_id=1, date=datetime.now(), chat=chat, from_user=user, text=text
        )
        self.__dict__.update(built.__dict__)
        object.__setattr__(self, "__pydantic_fields_set__", built.__pydantic_fields_set__)
        object.__setattr__(self, "__pydantic_extra__", built.__pydantic_extra__)
        object.__setattr__(self, "__pydantic_private__", built.__pydantic_private__)
        replies: list[tuple[str, dict]] = []
        edits: list[tuple[str, dict]] = []
        object.__setattr__(self, "replies", replies)
        object.__setattr__(self, "edits", edits)

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


class FakeCallback(CallbackQuery):
    """Stand-in for aiogram CallbackQuery, built on the real model.

    Subclassing the real ``CallbackQuery`` (via ``model_construct``, which
    skips its pydantic validation so a ``FakeMessage`` can stand in for
    ``message``) keeps ``isinstance(event, CallbackQuery)`` — the branch
    ``AccessMiddleware._deny`` uses to choose ``show_alert=True`` — true
    under test. A plain duck-typed double would always fail that check and
    silently exercise the wrong branch.
    """

    def __init__(
        self,
        data: str = "",
        user_id: int = 111,
        first_name: str = "Сергій",
        chat_type: str = "private",
    ) -> None:
        user = User(id=user_id, is_bot=False, first_name=first_name)
        message = FakeMessage(user_id=user_id, first_name=first_name, chat_type=chat_type)
        built = CallbackQuery.model_construct(
            id="fake-callback-id",
            from_user=user,
            chat_instance="fake-chat-instance",
            message=message,
            data=data,
        )
        self.__dict__.update(built.__dict__)
        object.__setattr__(self, "__pydantic_fields_set__", built.__pydantic_fields_set__)
        object.__setattr__(self, "__pydantic_extra__", built.__pydantic_extra__)
        object.__setattr__(self, "__pydantic_private__", built.__pydantic_private__)
        answers: list[tuple[str, bool]] = []
        object.__setattr__(self, "answers", answers)

    async def answer(self, text: str = "", show_alert: bool = False, **kwargs) -> None:
        self.answers.append((text, show_alert))


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=111))


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        TELEGRAM_BOT_TOKEN="123:ABC",
        ALLOWED_TELEGRAM_IDS="111,222",
        RECENT_EXPENSES_LIMIT=10,
    )


def kyiv(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    """A Kyiv wall-clock moment as the UTC-naive datetime the database stores."""
    local = datetime(year, month, day, hour, minute, tzinfo=KYIV)
    return local.astimezone(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def budget_db(tmp_path) -> Path:
    """A real SQLite file shaped like production: the singleton household,
    members Сергій and Оля, and the nine default categories. No expenses."""
    path = tmp_path / "budget.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with create_session_factory(engine)() as db_session:
        db_session.add(Household(id=SINGLETON_HOUSEHOLD_ID, name="Тест"))
        await db_session.flush()
        db_session.add_all(
            [
                Member(household_id=SINGLETON_HOUSEHOLD_ID, telegram_id=111, display_name="Сергій"),
                Member(household_id=SINGLETON_HOUSEHOLD_ID, telegram_id=222, display_name="Оля"),
            ]
        )
        await ensure_default_categories(db_session, SINGLETON_HOUSEHOLD_ID)
        await db_session.commit()
    await engine.dispose()
    return path


class BudgetWriter:
    """Writes test data through the bot's own read-write engine."""

    def __init__(self, path: Path) -> None:
        self.engine = create_engine(f"sqlite+aiosqlite:///{path}")
        self._factory = create_session_factory(self.engine)

    async def add_expense(
        self,
        *,
        category: str,
        member: str,
        amount: int,
        at: datetime,
        description: str | None = None,
    ) -> None:
        async with self._factory() as db_session:
            category_id = await db_session.scalar(
                select(Category.id).where(Category.name == category)
            )
            member_id = await db_session.scalar(
                select(Member.id).where(Member.display_name == member)
            )
            await create_expense(
                db_session,
                household_id=SINGLETON_HOUSEHOLD_ID,
                member_id=member_id,
                category_id=category_id,
                amount=amount,
                description=description,
                created_at=at,
            )
            await db_session.commit()

    async def add_member(self, display_name: str, telegram_id: int) -> None:
        async with self._factory() as db_session:
            db_session.add(
                Member(
                    household_id=SINGLETON_HOUSEHOLD_ID,
                    telegram_id=telegram_id,
                    display_name=display_name,
                )
            )
            await db_session.commit()


@pytest_asyncio.fixture
async def budget_writer(budget_db) -> BudgetWriter:
    writer = BudgetWriter(budget_db)
    yield writer
    await writer.engine.dispose()


@pytest_asyncio.fixture
async def early_september(budget_writer) -> None:
    """Five expenses around 1–15 September 2026, Kyiv time (UTC+3), in insertion order:

    | id | when (Kyiv)      | amount | category  | member | description  |
    |----|------------------|--------|-----------|--------|--------------|
    | 1  | 2026-09-01 09:00 | 250    | Їжа       | Сергій | кава         |
    | 2  | 2026-09-01 18:30 | 100    | Транспорт | Оля    | Таксі додому |
    | 3  | 2026-09-14 23:30 | 1200   | Їжа       | Оля    | Сільпо       |
    | 4  | 2026-09-15 00:10 | 600    | Розваги   | Сергій | Кіно         |
    | 5  | 2026-08-31 23:59 | 350    | Їжа       | Сергій | —            |
    """
    add = budget_writer.add_expense
    await add(
        category="Їжа", member="Сергій", amount=250, at=kyiv(2026, 9, 1, 9), description="кава"
    )
    await add(
        category="Транспорт",
        member="Оля",
        amount=100,
        at=kyiv(2026, 9, 1, 18, 30),
        description="Таксі додому",
    )
    await add(
        category="Їжа",
        member="Оля",
        amount=1200,
        at=kyiv(2026, 9, 14, 23, 30),
        description="Сільпо",
    )
    await add(
        category="Розваги",
        member="Сергій",
        amount=600,
        at=kyiv(2026, 9, 15, 0, 10),
        description="Кіно",
    )
    await add(category="Їжа", member="Сергій", amount=350, at=kyiv(2026, 8, 31, 23, 59))


@pytest_asyncio.fixture
async def readonly_session_factory(budget_db):
    engine = create_readonly_engine(budget_db)
    yield create_session_factory(engine)
    await engine.dispose()
