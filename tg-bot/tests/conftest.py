import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.db import create_engine, create_session_factory
from budget_bot.models import Base, Household


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
