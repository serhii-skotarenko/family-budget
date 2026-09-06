# Telegram Budget Bot MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Побудувати Telegram-бота, який дозволяє двом користувачам однієї родини логувати витрати в гривнях по категоріях, переглядати/фільтрувати/редагувати/видаляти записи та отримувати текстові звіти за тиждень/місяць/рік.

**Architecture:** Однопроцесний aiogram 3 бот у режимі long polling. Три шари: чисті доменні функції (періоди, валідація сум, форматування) → сервіси, що працюють з `AsyncSession` (households, categories, expenses, reports) → aiogram-хендлери, які лише збирають ввід і рендерять текст. Доступ і сесія БД впорскуються через outer-middleware, тож жоден хендлер не перевіряє whitelist самостійно. Дані — SQLite-файл на змонтованому томі, схема під керуванням Alembic.

**Tech Stack:** Python 3.12, aiogram 3.x, SQLAlchemy 2.0 (async) + aiosqlite, Alembic, pydantic-settings, pytest + pytest-asyncio, ruff + black, Docker.

## Global Constraints

Ці правила діють у **кожній** задачі — не повторюються в описах окремих кроків.

- **Джерело правди по скоупу:** `docs/requirements.md`. Якщо код і документ розійдуться — правити код під документ.
- **Python 3.12+**, увесь код бота живе під `tg-bot/`.
- **Валюта — тільки UAH, тільки цілі гривні** (`int`), без копійок: і при введенні, і в БД, і у звітах.
- **Таймзона `Europe/Kyiv`** для всіх меж періодів і для показу дат користувачу. У БД `datetime` зберігаються як **UTC-naive** (без tzinfo) — SQLite не зберігає offset, тому tz-aware значення туди писати заборонено.
- **Тиждень — календарний, Пн–Нд** за Europe/Kyiv.
- **Одне домогосподарство (household)** на інсталяцію. Whitelist з env `ALLOWED_TELEGRAM_IDS` (comma-separated), перевіряється на кожному апдейті.
- **Обидва користувачі можуть редагувати й видаляти будь-який запис.** `member_id` (автор) при редагуванні **ніколи** не змінюється; змінюються тільки `updated_by_id` і `updated_at`.
- **Бот ніколи не пише першим** — жодних проактивних сповіщень, крон-джобів, розсилок.
- **Базові категорії (рівно 9, у цьому порядку):** `Їжа, Транспорт, Комунальні, Оренда житла, Розваги, Здоров'я, Одяг, Діти, Інше`.
- **Автор у списках і звітах показується як `display_name`**, не як Telegram username.
- **Тексти для користувача — українською.** Імена змінних/функцій/файлів, докстрінги і commit-меседжі — англійською.
- **Commit-меседжі:** conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- **Форматування/лінт:** `black` (line-length 100) + `ruff`. Перед комітом задачі — `ruff check tg-bot && black --check tg-bot`.
- **Деплой портативний:** Dockerfile + конфіг через env + том під SQLite. Жодних файлів, специфічних для Railway/Fly.io.
- **Усі рядки для користувача, які містять текст від користувача** (опис витрати, назва категорії, display_name), проганяються через `html.escape` — parse mode HTML.
- **TDD:** тест → запуск (падає) → мінімальна реалізація → запуск (зелений) → коміт. Не писати реалізацію раніше за тест.
- **Всі команди запускаються з `tg-bot/`** якщо не вказано інше.

---

## File Structure

```
tg-bot/
├── pyproject.toml                       # deps, black/ruff/pytest config, package metadata
├── .env.example                         # шаблон конфігу
├── .gitignore
├── .dockerignore
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh                 # alembic upgrade head → exec CMD
├── README.md
├── alembic.ini
├── alembic/
│   ├── env.py                           # async-варіант env.py
│   └── versions/0001_initial_schema.py
├── src/budget_bot/
│   ├── __init__.py
│   ├── __main__.py                      # composition root: engine, Bot, Dispatcher, polling
│   ├── config.py                        # Settings (pydantic-settings)
│   ├── clock.py                         # utcnow() → UTC-naive
│   ├── db.py                            # engine + session factory + PRAGMA foreign_keys
│   ├── models.py                        # Household, Member, Category, Expense
│   ├── amounts.py                       # parse_amount / format_amount
│   ├── periods.py                       # Period, PeriodRange, межі в Europe/Kyiv
│   ├── formatting.py                    # рендер витрат, карток, звітів
│   ├── services/
│   │   ├── __init__.py
│   │   ├── access.py                    # household/member bootstrap + дефолтні категорії
│   │   ├── categories.py                # список / додавання власної
│   │   ├── expenses.py                  # create / get / list+filters / update / delete
│   │   └── reports.py                   # агрегація за період
│   └── bot/
│       ├── __init__.py
│       ├── middlewares.py               # DbSessionMiddleware, AccessMiddleware
│       ├── callbacks.py                 # CallbackData-фабрики
│       ├── keyboards.py                 # головне меню, категорії, підтвердження
│       └── handlers/
│           ├── __init__.py              # build_router() — порядок роутерів
│           ├── common.py                # /start, /cancel, головне меню
│           ├── categories.py            # /categories + додавання категорії
│           ├── add_expense.py           # FSM /add
│           ├── expense_list.py          # /list + картка запису
│           ├── filters.py               # /filter
│           ├── expense_edit.py          # редагування запису
│           ├── expense_delete.py        # видалення з підтвердженням
│           └── reports.py               # /report
└── tests/
    ├── conftest.py                      # session fixture, FakeMessage/FakeCallback, state
    ├── test_config.py
    ├── test_models.py
    ├── test_migrations.py
    ├── test_amounts.py
    ├── test_periods.py
    ├── test_services_access.py
    ├── test_services_categories.py
    ├── test_services_expenses.py
    ├── test_services_reports.py
    ├── test_formatting.py
    ├── test_middlewares.py
    ├── test_handlers_common.py
    ├── test_handlers_categories.py
    ├── test_handlers_add_expense.py
    ├── test_handlers_expense_list.py
    ├── test_handlers_filters.py
    ├── test_handlers_expense_edit.py
    ├── test_handlers_expense_delete.py
    └── test_handlers_reports.py
```

**Чому так:** доменні модулі (`amounts`, `periods`, `formatting`) — чисті функції без БД, тестуються миттєво і покривають найризикованішу логіку (межі тижня через DST, валідація сум, відсотки у звіті). Сервіси не знають про aiogram, хендлери не пишуть SQL. Це дозволяє тестувати ~80% MVP без жодного мока Telegram API.

---

## Покриття user stories

| Story | Задача |
|---|---|
| US1.1 whitelist + /start | 1, 2, 5, 10 |
| US2.1 базові категорії | 4, 11 |
| US2.2 власна категорія | 4, 11 |
| US3.1 покроковий діалог /add | 3, 6, 12 |
| US4.1 список останніх | 6, 9, 13 |
| US4.2 фільтрація | 3, 6, 14 |
| US5.1 редагування | 7, 15 |
| US6.1 видалення | 7, 16 |
| US7.1 звіти | 3, 8, 9, 17 |
| Деплой (CLAUDE.md) | 18 |

---

### Task 1: Project scaffolding and configuration

**Files:**
- Create: `tg-bot/pyproject.toml`
- Create: `tg-bot/.gitignore`
- Create: `tg-bot/.env.example`
- Create: `tg-bot/src/budget_bot/__init__.py`
- Create: `tg-bot/src/budget_bot/config.py`
- Test: `tg-bot/tests/test_config.py`

**Interfaces:**
- Consumes: нічого (перша задача).
- Produces: `budget_bot.config.Settings` — pydantic-settings клас з полями `telegram_bot_token: str`, `allowed_telegram_ids_raw: str`, `household_name: str`, `database_path: Path`, `recent_expenses_limit: int`; властивості `allowed_telegram_ids -> frozenset[int]` і `database_url -> str`.

- [ ] **Step 1: Створити структуру каталогів і `pyproject.toml`**

```bash
mkdir -p tg-bot/src/budget_bot tg-bot/tests
touch tg-bot/src/budget_bot/__init__.py
# tests/ is a package so handler tests can do `from tests.conftest import FakeMessage`
touch tg-bot/tests/__init__.py
```

`tg-bot/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "budget-bot"
version = "0.1.0"
description = "Family budget Telegram bot"
requires-python = ">=3.12"
dependencies = [
    "aiogram>=3.15,<4",
    "sqlalchemy[asyncio]>=2.0.36",
    "aiosqlite>=0.20",
    "alembic>=1.14",
    "pydantic-settings>=2.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "black>=24.10",
]

[tool.hatch.build.targets.wheel]
packages = ["src/budget_bot"]

[tool.black]
line-length = 100
target-version = ["py312"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`tg-bot/.gitignore`:

```gitignore
__pycache__/
*.py[cod]
.venv/
.env
data/
.pytest_cache/
.ruff_cache/
*.egg-info/
```

- [ ] **Step 2: Створити віртуальне оточення і встановити залежності**

```bash
cd tg-bot && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Expected: інсталяція проходить без помилок, `budget_bot` імпортується.

- [ ] **Step 3: Написати падаючий тест конфігу**

`tg-bot/tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from budget_bot.config import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "TELEGRAM_BOT_TOKEN": "123:ABC",
        "ALLOWED_TELEGRAM_IDS": "111,222",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_parses_comma_separated_ids():
    assert make_settings().allowed_telegram_ids == frozenset({111, 222})


def test_tolerates_spaces_and_trailing_comma():
    settings = make_settings(ALLOWED_TELEGRAM_IDS=" 111 , 222 ,")
    assert settings.allowed_telegram_ids == frozenset({111, 222})


def test_rejects_empty_id_list():
    with pytest.raises(ValidationError):
        make_settings(ALLOWED_TELEGRAM_IDS="  ")


def test_rejects_non_numeric_id():
    with pytest.raises(ValidationError):
        make_settings(ALLOWED_TELEGRAM_IDS="111,abc")


def test_builds_sqlite_async_url():
    settings = make_settings(DATABASE_PATH="data/budget.sqlite3")
    assert settings.database_url == "sqlite+aiosqlite:///data/budget.sqlite3"


def test_defaults():
    settings = make_settings()
    assert settings.household_name == "Сім'я"
    assert settings.recent_expenses_limit == 10
```

- [ ] **Step 4: Запустити тести — мають впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.config'`

- [ ] **Step 5: Реалізувати `config.py`**

`tg-bot/src/budget_bot/config.py`:

```python
"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    ``allowed_telegram_ids_raw`` is kept as a plain string on purpose:
    pydantic-settings tries to JSON-decode env values for complex field types,
    which would break a simple comma-separated list.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    allowed_telegram_ids_raw: str = Field(alias="ALLOWED_TELEGRAM_IDS")
    household_name: str = Field(default="Сім'я", alias="HOUSEHOLD_NAME")
    database_path: Path = Field(default=Path("data/budget.sqlite3"), alias="DATABASE_PATH")
    recent_expenses_limit: int = Field(default=10, alias="RECENT_EXPENSES_LIMIT")

    @property
    def allowed_telegram_ids(self) -> frozenset[int]:
        parts = [chunk.strip() for chunk in self.allowed_telegram_ids_raw.split(",")]
        return frozenset(int(part) for part in parts if part)

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path}"

    @model_validator(mode="after")
    def _validate_allowed_ids(self) -> "Settings":
        try:
            ids = self.allowed_telegram_ids
        except ValueError as exc:
            raise ValueError("ALLOWED_TELEGRAM_IDS must be comma-separated integers") from exc
        if not ids:
            raise ValueError("ALLOWED_TELEGRAM_IDS must contain at least one Telegram ID")
        return self
```

- [ ] **Step 6: Створити `.env.example`**

`tg-bot/.env.example`:

```dotenv
# Токен від @BotFather
TELEGRAM_BOT_TOKEN=

# Telegram ID дозволених користувачів, через кому (дізнатись можна у @userinfobot)
ALLOWED_TELEGRAM_IDS=

# Назва домогосподарства (опційно)
HOUSEHOLD_NAME=Сім'я

# Шлях до файлу SQLite (у Docker — /data/budget.sqlite3)
DATABASE_PATH=data/budget.sqlite3

# Скільки останніх витрат показує /list
RECENT_EXPENSES_LIMIT=10
```

- [ ] **Step 7: Запустити тести — мають пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_config.py -v`
Expected: 6 passed

- [ ] **Step 8: Коміт**

```bash
git add tg-bot/pyproject.toml tg-bot/.gitignore tg-bot/.env.example tg-bot/src tg-bot/tests
git commit -m "feat: add project scaffolding and env-based configuration"
```

---

### Task 2: Data model, session factory and initial migration

**Files:**
- Create: `tg-bot/src/budget_bot/clock.py`
- Create: `tg-bot/src/budget_bot/models.py`
- Create: `tg-bot/src/budget_bot/db.py`
- Create: `tg-bot/alembic.ini`
- Create: `tg-bot/alembic/env.py`
- Create: `tg-bot/alembic/script.py.mako`
- Create: `tg-bot/alembic/versions/0001_initial_schema.py`
- Create: `tg-bot/tests/conftest.py`
- Test: `tg-bot/tests/test_models.py`, `tg-bot/tests/test_migrations.py`

**Interfaces:**
- Consumes: `budget_bot.config.Settings.database_url`.
- Produces:
  - `budget_bot.clock.utcnow() -> datetime` (UTC-naive).
  - `budget_bot.models`: `Base`, `Household(id, name, created_at)`, `Member(id, household_id, telegram_id, display_name, created_at)`, `Category(id, household_id, name, name_normalized, is_custom, created_at)`, `Expense(id, household_id, member_id, category_id, amount, description, created_at, updated_by_id, updated_at)` + relationships `Expense.category`, `Expense.author`, `Expense.updated_by` (усі `lazy="selectin"`).
  - `budget_bot.db.create_engine(database_url) -> AsyncEngine`, `budget_bot.db.create_session_factory(engine) -> async_sessionmaker[AsyncSession]`.
  - `tests/conftest.py`: фікстура `session` (in-memory БД зі створеною схемою).

- [ ] **Step 1: Написати падаючий тест моделей**

`tg-bot/tests/test_models.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from budget_bot.clock import utcnow
from budget_bot.models import Category, Expense, Household, Member


async def test_expense_relationships_load_without_lazy_io(session):
    household = Household(name="Test")
    session.add(household)
    await session.flush()

    member = Member(household_id=household.id, telegram_id=111, display_name="Сергій")
    category = Category(household_id=household.id, name="Їжа", name_normalized="їжа")
    session.add_all([member, category])
    await session.flush()

    session.add(
        Expense(
            household_id=household.id,
            member_id=member.id,
            category_id=category.id,
            amount=250,
            description="кава",
            created_at=utcnow(),
        )
    )
    await session.commit()

    expense = (await session.execute(select(Expense))).scalar_one()
    assert expense.category.name == "Їжа"
    assert expense.author.display_name == "Сергій"
    assert expense.updated_by is None
    assert expense.amount == 250


async def test_category_name_is_unique_per_household(session):
    household = Household(name="Test")
    session.add(household)
    await session.flush()

    session.add(Category(household_id=household.id, name="Кава", name_normalized="кава"))
    await session.flush()
    session.add(Category(household_id=household.id, name="КАВА", name_normalized="кава"))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_telegram_id_is_unique(session):
    household = Household(name="Test")
    session.add(household)
    await session.flush()

    session.add(Member(household_id=household.id, telegram_id=111, display_name="A"))
    await session.flush()
    session.add(Member(household_id=household.id, telegram_id=111, display_name="B"))

    with pytest.raises(IntegrityError):
        await session.flush()


def test_utcnow_is_naive():
    assert utcnow().tzinfo is None
```

- [ ] **Step 2: Написати `conftest.py` з фікстурою сесії**

`tg-bot/tests/conftest.py`:

```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.db import create_engine, create_session_factory
from budget_bot.models import Base


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
```

- [ ] **Step 3: Запустити тести — мають впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.clock'`

- [ ] **Step 4: Реалізувати `clock.py`, `models.py`, `db.py`**

`tg-bot/src/budget_bot/clock.py`:

```python
"""Single source of 'now' for the whole app.

Everything stored in SQLite is UTC-naive: SQLite has no timezone type and the
SQLAlchemy SQLite dialect silently drops tzinfo, so we drop it explicitly.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
```

`tg-bot/src/budget_bot/models.py`:

```python
"""SQLAlchemy models. All datetimes are UTC-naive (see budget_bot.clock)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from budget_bot.clock import utcnow


class Base(DeclarativeBase):
    pass


class Household(Base):
    __tablename__ = "households"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("telegram_id", name="uq_members_telegram_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    display_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("household_id", "name_normalized", name="uq_categories_household_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    # Lowercased via Python str.casefold(): SQLite's LOWER() is ASCII-only and
    # would not match Cyrillic duplicates.
    name_normalized: Mapped[str] = mapped_column(String(60))
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_household_created", "household_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    # Author. Never changes, even when the other member edits the record.
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[int]
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # lazy="selectin" keeps handlers free of explicit eager-loading options;
    # plain lazy loading would raise MissingGreenlet under asyncio.
    category: Mapped[Category] = relationship(lazy="selectin")
    author: Mapped[Member] = relationship(lazy="selectin", foreign_keys=[member_id])
    updated_by: Mapped[Member | None] = relationship(lazy="selectin", foreign_keys=[updated_by_id])
```

`tg-bot/src/budget_bot/db.py`:

```python
"""Async engine and session factory."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- [ ] **Step 5: Запустити тести моделей — мають пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_models.py -v`
Expected: 4 passed

- [ ] **Step 6: Написати падаючий тест міграції**

`tg-bot/tests/test_migrations.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from budget_bot.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_head_matches_models(tmp_path):
    """The migration and the models must describe the same schema."""
    db_path = tmp_path / "migrated.sqlite3"
    result = subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_PATH": str(db_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    inspector = inspect(create_engine(f"sqlite:///{db_path}"))
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
```

- [ ] **Step 7: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_migrations.py -v`
Expected: FAIL — alembic не налаштований (`No config file 'alembic.ini' found`)

- [ ] **Step 8: Ініціалізувати Alembic і налаштувати async env**

```bash
cd tg-bot && .venv/bin/alembic init -t async alembic
```

Далі відредагувати `tg-bot/alembic.ini` — прибрати рядок `sqlalchemy.url` (URL береться з env) і залишити:

```ini
[alembic]
script_location = alembic
prepend_sys_path = src
file_template = %%(rev)s_%%(slug)s
```

`tg-bot/alembic/env.py` — замінити повністю на:

```python
import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from budget_bot.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_path = Path(os.environ.get("DATABASE_PATH", "data/budget.sqlite3"))
database_path.parent.mkdir(parents=True, exist_ok=True)
config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")

target_metadata = Base.metadata


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite cannot ALTER most things in place; batch mode rewrites tables.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 9: Написати початкову міграцію**

`tg-bot/alembic/versions/0001_initial_schema.py`:

```python
"""initial schema

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("telegram_id", name="uq_members_telegram_id"),
    )
    op.create_index("ix_members_household_id", "members", ["household_id"])
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("name_normalized", sa.String(length=60), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("household_id", "name_normalized", name="uq_categories_household_name"),
    )
    op.create_index("ix_categories_household_id", "categories", ["household_id"])
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_expenses_household_id", "expenses", ["household_id"])
    op.create_index("ix_expenses_household_created", "expenses", ["household_id", "created_at"])


def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("categories")
    op.drop_table("members")
    op.drop_table("households")
```

- [ ] **Step 10: Запустити всі тести — мають пройти**

Run: `cd tg-bot && .venv/bin/pytest -v`
Expected: усі passed (config + models + migrations)

- [ ] **Step 11: Коміт**

```bash
git add tg-bot/src/budget_bot tg-bot/alembic tg-bot/alembic.ini tg-bot/tests
git commit -m "feat: add data model, async session factory and initial migration"
```

---

### Task 3: Domain helpers — amounts and Kyiv period boundaries

**Files:**
- Create: `tg-bot/src/budget_bot/amounts.py`
- Create: `tg-bot/src/budget_bot/periods.py`
- Test: `tg-bot/tests/test_amounts.py`, `tg-bot/tests/test_periods.py`

**Interfaces:**
- Consumes: нічого (чисті функції).
- Produces:
  - `budget_bot.amounts`: `MAX_AMOUNT: int`, `AmountError(ValueError)`, `parse_amount(raw: str) -> int`, `format_amount(value: int) -> str`.
  - `budget_bot.periods`: `KYIV: ZoneInfo`, `Period(StrEnum)` зі значеннями `today|week|month|year`, `PeriodRange(start: datetime, end: datetime, label: str)` (frozen dataclass, UTC-naive, `[start, end)`), `PERIOD_TITLES: dict[Period, str]`, `period_range(period: Period, now_utc: datetime) -> PeriodRange`, `parse_custom_range(raw: str) -> PeriodRange`, `to_kyiv(dt_utc: datetime) -> datetime`, `format_date_short(dt_utc) -> str`, `format_datetime(dt_utc) -> str`.

- [ ] **Step 1: Написати падаючі тести сум**

`tg-bot/tests/test_amounts.py`:

```python
import pytest

from budget_bot.amounts import AmountError, format_amount, parse_amount


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100", 100),
        ("  250  ", 250),
        ("1 000", 1000),
        ("1\u00a0000", 1000),
        ("1", 1),
    ],
)
def test_parses_positive_integers(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "abc", "12.5", "12,5", "-5", "0", "١٢٣", "10000001", "1e3"],
)
def test_rejects_invalid_amounts(raw):
    with pytest.raises(AmountError):
        parse_amount(raw)


def test_format_amount_groups_thousands_with_nbsp():
    assert format_amount(12500) == "12\u00a0500\u00a0₴"
    assert format_amount(250) == "250\u00a0₴"
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_amounts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.amounts'`

- [ ] **Step 3: Реалізувати `amounts.py`**

```python
"""Parsing and rendering of hryvnia amounts. Whole UAH only, no kopiykas."""

import re

MAX_AMOUNT = 10_000_000

_DIGITS = re.compile(r"\d+", re.ASCII)
_SEPARATORS = str.maketrans({" ": "", "\u00a0": "", "\u202f": "", "'": ""})


class AmountError(ValueError):
    """Raised when user input is not a valid whole-hryvnia amount."""


def parse_amount(raw: str) -> int:
    cleaned = raw.strip().translate(_SEPARATORS)
    if not _DIGITS.fullmatch(cleaned):
        raise AmountError("Сума має бути цілим числом гривень, наприклад: 250")
    value = int(cleaned)
    if value <= 0:
        raise AmountError("Сума має бути більшою за нуль.")
    if value > MAX_AMOUNT:
        raise AmountError(f"Сума завелика. Максимум — {format_amount(MAX_AMOUNT)}.")
    return value


def format_amount(value: int) -> str:
    return f"{value:,}".replace(",", "\u00a0") + "\u00a0₴"
```

- [ ] **Step 4: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_amounts.py -v`
Expected: 16 passed

- [ ] **Step 5: Написати падаючі тести періодів**

`tg-bot/tests/test_periods.py`:

```python
from datetime import datetime

import pytest

from budget_bot.periods import (
    Period,
    format_date_short,
    format_datetime,
    parse_custom_range,
    period_range,
    to_kyiv,
)

# 2026-09-07 is a Monday. Kyiv is UTC+3 (EEST) in September.
NOW = datetime(2026, 9, 7, 9, 0)  # 12:00 Kyiv


def test_to_kyiv_adds_three_hours_in_summer():
    assert to_kyiv(NOW).hour == 12


def test_today_range():
    result = period_range(Period.TODAY, NOW)
    assert result.start == datetime(2026, 9, 6, 21, 0)
    assert result.end == datetime(2026, 9, 7, 21, 0)
    assert result.label == "сьогодні (07.09.2026)"


def test_week_starts_on_monday():
    result = period_range(Period.WEEK, NOW)
    assert result.start == datetime(2026, 9, 6, 21, 0)  # Mon 07.09 00:00 Kyiv
    assert result.end == datetime(2026, 9, 13, 21, 0)  # Mon 14.09 00:00 Kyiv
    assert result.label == "поточний тиждень (07.09–13.09.2026)"


def test_week_containing_sunday_still_starts_on_monday():
    sunday = datetime(2026, 9, 13, 9, 0)  # Sunday 12:00 Kyiv
    result = period_range(Period.WEEK, sunday)
    assert result.start == datetime(2026, 9, 6, 21, 0)
    assert result.end == datetime(2026, 9, 13, 21, 0)


def test_month_range_crossing_dst_end():
    # DST ends on 2026-10-25: October starts at UTC+3 and ends at UTC+2.
    october = datetime(2026, 10, 10, 9, 0)
    result = period_range(Period.MONTH, october)
    assert result.start == datetime(2026, 9, 30, 21, 0)
    assert result.end == datetime(2026, 10, 31, 22, 0)
    assert result.label == "поточний місяць (жовтень 2026)"


def test_year_range():
    result = period_range(Period.YEAR, NOW)
    assert result.start == datetime(2025, 12, 31, 22, 0)  # 01.01.2026 00:00 Kyiv (UTC+2)
    assert result.end == datetime(2026, 12, 31, 22, 0)
    assert result.label == "поточний рік (2026)"


def test_parse_custom_range_is_inclusive_of_the_last_day():
    result = parse_custom_range("01.09.2026-15.09.2026")
    assert result.start == datetime(2026, 8, 31, 21, 0)
    assert result.end == datetime(2026, 9, 15, 21, 0)
    assert result.label == "01.09.2026–15.09.2026"


@pytest.mark.parametrize(
    "raw",
    ["", "01.09.2026", "abc-def", "15.09.2026-01.09.2026", "32.09.2026-01.10.2026"],
)
def test_parse_custom_range_rejects_bad_input(raw):
    with pytest.raises(ValueError):
        parse_custom_range(raw)


def test_date_formatting_uses_kyiv_time():
    assert format_date_short(NOW) == "07.09"
    assert format_datetime(NOW) == "07.09.2026 12:00"
```

- [ ] **Step 6: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_periods.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.periods'`

- [ ] **Step 7: Реалізувати `periods.py`**

```python
"""Calendar period boundaries in Europe/Kyiv, returned as UTC-naive ranges.

Boundaries are built in the `date` domain and only then converted to UTC, so
DST transitions (which happen at 03:00/04:00 local, never at midnight) cannot
shift a period start by an hour.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")

MONTHS_UK = (
    "січень",
    "лютий",
    "березень",
    "квітень",
    "травень",
    "червень",
    "липень",
    "серпень",
    "вересень",
    "жовтень",
    "листопад",
    "грудень",
)


class Period(StrEnum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


PERIOD_TITLES = {
    Period.TODAY: "Сьогодні",
    Period.WEEK: "Поточний тиждень",
    Period.MONTH: "Поточний місяць",
    Period.YEAR: "Поточний рік",
}


@dataclass(frozen=True)
class PeriodRange:
    """Half-open [start, end) range of UTC-naive datetimes."""

    start: datetime
    end: datetime
    label: str


def to_kyiv(dt_utc: datetime) -> datetime:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(KYIV)


def _kyiv_midnight_as_utc(day: date) -> datetime:
    local = datetime(day.year, day.month, day.day, tzinfo=KYIV)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def period_range(period: Period, now_utc: datetime) -> PeriodRange:
    today = to_kyiv(now_utc).date()

    if period is Period.TODAY:
        first, last = today, today
        label = f"сьогодні ({first:%d.%m.%Y})"
    elif period is Period.WEEK:
        first = today - timedelta(days=today.weekday())
        last = first + timedelta(days=6)
        label = f"поточний тиждень ({first:%d.%m}–{last:%d.%m.%Y})"
    elif period is Period.MONTH:
        first = today.replace(day=1)
        last = (first + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        label = f"поточний місяць ({MONTHS_UK[first.month - 1]} {first.year})"
    else:
        first = date(today.year, 1, 1)
        last = date(today.year, 12, 31)
        label = f"поточний рік ({first.year})"

    return PeriodRange(
        start=_kyiv_midnight_as_utc(first),
        end=_kyiv_midnight_as_utc(last + timedelta(days=1)),
        label=label,
    )


def parse_custom_range(raw: str) -> PeriodRange:
    """Parse 'DD.MM.YYYY-DD.MM.YYYY' into an inclusive-of-last-day range."""
    parts = [chunk.strip() for chunk in raw.replace("—", "-").replace("–", "-").split("-")]
    if len(parts) != 2 or not all(parts):
        raise ValueError("Формат: ДД.ММ.РРРР-ДД.ММ.РРРР, наприклад 01.09.2026-15.09.2026")
    try:
        first = datetime.strptime(parts[0], "%d.%m.%Y").date()
        last = datetime.strptime(parts[1], "%d.%m.%Y").date()
    except ValueError as exc:
        raise ValueError(
            "Формат: ДД.ММ.РРРР-ДД.ММ.РРРР, наприклад 01.09.2026-15.09.2026"
        ) from exc
    if last < first:
        raise ValueError("Кінцева дата має бути не раніше за початкову.")
    return PeriodRange(
        start=_kyiv_midnight_as_utc(first),
        end=_kyiv_midnight_as_utc(last + timedelta(days=1)),
        label=f"{first:%d.%m.%Y}–{last:%d.%m.%Y}",
    )


def format_date_short(dt_utc: datetime) -> str:
    return f"{to_kyiv(dt_utc):%d.%m}"


def format_datetime(dt_utc: datetime) -> str:
    return f"{to_kyiv(dt_utc):%d.%m.%Y %H:%M}"
```

- [ ] **Step 8: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_periods.py -v`
Expected: усі passed

- [ ] **Step 9: Коміт**

```bash
git add tg-bot/src/budget_bot/amounts.py tg-bot/src/budget_bot/periods.py tg-bot/tests/test_amounts.py tg-bot/tests/test_periods.py
git commit -m "feat: add amount validation and Kyiv calendar period helpers"
```

---
### Task 4: Categories service

**Files:**
- Create: `tg-bot/src/budget_bot/services/__init__.py`
- Create: `tg-bot/src/budget_bot/services/categories.py`
- Modify: `tg-bot/tests/conftest.py` (додати фікстуру `household`)
- Test: `tg-bot/tests/test_services_categories.py`

**Interfaces:**
- Consumes: `budget_bot.models.Category`.
- Produces: `budget_bot.services.categories` з
  `DEFAULT_CATEGORIES: tuple[str, ...]` (9 назв),
  `MAX_NAME_LENGTH: int = 60`,
  `CategoryNameError(ValueError)`, `DuplicateCategoryError(ValueError)` (має атрибут `.name`),
  `normalize_category_name(name: str) -> str`,
  `ensure_default_categories(session, household_id: int) -> None`,
  `list_categories(session, household_id: int) -> list[Category]`,
  `get_category(session, household_id: int, category_id: int) -> Category | None`,
  `add_category(session, household_id: int, raw_name: str) -> Category`.

- [ ] **Step 1: Додати фікстуру `household` у `conftest.py`**

Додати в кінець `tg-bot/tests/conftest.py`:

```python
from budget_bot.models import Household


@pytest_asyncio.fixture
async def household(session) -> Household:
    item = Household(name="Тест")
    session.add(item)
    await session.flush()
    return item
```

- [ ] **Step 2: Написати падаючий тест**

`tg-bot/tests/test_services_categories.py`:

```python
import pytest

from budget_bot.services.categories import (
    DEFAULT_CATEGORIES,
    CategoryNameError,
    DuplicateCategoryError,
    add_category,
    ensure_default_categories,
    get_category,
    list_categories,
    normalize_category_name,
)


async def test_seeds_nine_default_categories_in_canonical_order(session, household):
    await ensure_default_categories(session, household.id)

    names = [category.name for category in await list_categories(session, household.id)]
    assert names == list(DEFAULT_CATEGORIES)
    assert len(names) == 9


async def test_seeding_is_idempotent(session, household):
    await ensure_default_categories(session, household.id)
    await ensure_default_categories(session, household.id)

    assert len(await list_categories(session, household.id)) == 9


async def test_custom_categories_come_after_defaults(session, household):
    await ensure_default_categories(session, household.id)
    await add_category(session, household.id, "Кава")

    categories = await list_categories(session, household.id)
    assert categories[-1].name == "Кава"
    assert categories[-1].is_custom is True
    assert categories[0].is_custom is False


async def test_rejects_case_insensitive_duplicate_of_default(session, household):
    await ensure_default_categories(session, household.id)

    with pytest.raises(DuplicateCategoryError) as exc_info:
        await add_category(session, household.id, "  їжа ")
    assert exc_info.value.name == "Їжа"


async def test_rejects_case_insensitive_duplicate_of_custom(session, household):
    await add_category(session, household.id, "Кава")

    with pytest.raises(DuplicateCategoryError):
        await add_category(session, household.id, "КАВА")


async def test_collapses_inner_whitespace(session, household):
    category = await add_category(session, household.id, "  Дитячий   садок ")
    assert category.name == "Дитячий садок"


@pytest.mark.parametrize("raw", ["", "   ", "x" * 61])
async def test_rejects_invalid_names(session, household, raw):
    with pytest.raises(CategoryNameError):
        await add_category(session, household.id, raw)


async def test_get_category_is_scoped_to_household(session, household):
    category = await add_category(session, household.id, "Кава")

    assert await get_category(session, household.id, category.id) is not None
    assert await get_category(session, household.id + 1, category.id) is None


def test_normalization_handles_cyrillic_case():
    assert normalize_category_name(" ЇЖА ") == normalize_category_name("їжа")
```

- [ ] **Step 3: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_categories.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.services'`

- [ ] **Step 4: Реалізувати сервіс**

```bash
mkdir -p tg-bot/src/budget_bot/services && touch tg-bot/src/budget_bot/services/__init__.py
```

`tg-bot/src/budget_bot/services/categories.py`:

```python
"""Category list management for a household."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Category

DEFAULT_CATEGORIES: tuple[str, ...] = (
    "Їжа",
    "Транспорт",
    "Комунальні",
    "Оренда житла",
    "Розваги",
    "Здоров'я",
    "Одяг",
    "Діти",
    "Інше",
)

MAX_NAME_LENGTH = 60


class CategoryNameError(ValueError):
    """Raised when a category name is empty or too long."""


class DuplicateCategoryError(ValueError):
    """Raised when a category with the same normalized name already exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Категорія «{name}» вже існує.")


def normalize_category_name(name: str) -> str:
    """Collapse whitespace and casefold.

    str.casefold() is used instead of SQL LOWER(): SQLite's LOWER() only
    handles ASCII, so 'ЇЖА' and 'їжа' would not collide in the database.
    """
    return " ".join(name.split()).casefold()


async def ensure_default_categories(session: AsyncSession, household_id: int) -> None:
    existing = await session.scalar(
        select(func.count()).select_from(Category).where(Category.household_id == household_id)
    )
    if existing:
        return
    session.add_all(
        [
            Category(
                household_id=household_id,
                name=name,
                name_normalized=normalize_category_name(name),
                is_custom=False,
            )
            for name in DEFAULT_CATEGORIES
        ]
    )
    await session.flush()


async def list_categories(session: AsyncSession, household_id: int) -> list[Category]:
    """Defaults first (in canonical order), then custom ones by creation order."""
    result = await session.scalars(
        select(Category)
        .where(Category.household_id == household_id)
        .order_by(Category.is_custom, Category.id)
    )
    return list(result)


async def get_category(
    session: AsyncSession, household_id: int, category_id: int
) -> Category | None:
    return await session.scalar(
        select(Category).where(
            Category.id == category_id, Category.household_id == household_id
        )
    )


async def add_category(session: AsyncSession, household_id: int, raw_name: str) -> Category:
    name = " ".join(raw_name.split())
    if not name:
        raise CategoryNameError("Назва категорії не може бути порожньою.")
    if len(name) > MAX_NAME_LENGTH:
        raise CategoryNameError(f"Назва задовга — максимум {MAX_NAME_LENGTH} символів.")

    normalized = normalize_category_name(name)
    duplicate = await session.scalar(
        select(Category).where(
            Category.household_id == household_id, Category.name_normalized == normalized
        )
    )
    if duplicate is not None:
        raise DuplicateCategoryError(duplicate.name)

    category = Category(
        household_id=household_id, name=name, name_normalized=normalized, is_custom=True
    )
    session.add(category)
    await session.flush()
    return category
```

- [ ] **Step 5: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_categories.py -v`
Expected: усі passed

- [ ] **Step 6: Коміт**

```bash
git add tg-bot/src/budget_bot/services tg-bot/tests
git commit -m "feat: add category service with default seeding and duplicate detection"
```

---

### Task 5: Household and member bootstrap

**Files:**
- Create: `tg-bot/src/budget_bot/services/access.py`
- Modify: `tg-bot/tests/conftest.py` (додати фікстури `member`, `category`)
- Test: `tg-bot/tests/test_services_access.py`

**Interfaces:**
- Consumes: `budget_bot.services.categories.ensure_default_categories`, `budget_bot.models.{Household, Member}`.
- Produces: `budget_bot.services.access` з
  `get_or_create_household(session, name: str) -> Household`,
  `resolve_member(session, *, telegram_id: int, display_name: str, household_name: str) -> Member`,
  `list_members(session, household_id: int) -> list[Member]`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_services_access.py`:

```python
from sqlalchemy import func, select

from budget_bot.models import Category, Household, Member
from budget_bot.services.access import get_or_create_household, list_members, resolve_member


async def test_creates_household_with_default_categories_on_first_call(session):
    household = await get_or_create_household(session, "Сім'я")

    assert household.name == "Сім'я"
    count = await session.scalar(
        select(func.count()).select_from(Category).where(Category.household_id == household.id)
    )
    assert count == 9


async def test_reuses_the_single_household(session):
    first = await get_or_create_household(session, "Сім'я")
    second = await get_or_create_household(session, "Інша назва")

    assert first.id == second.id
    assert second.name == "Сім'я"
    assert await session.scalar(select(func.count()).select_from(Household)) == 1


async def test_both_members_join_the_same_household(session):
    one = await resolve_member(
        session, telegram_id=111, display_name="Сергій", household_name="Сім'я"
    )
    two = await resolve_member(
        session, telegram_id=222, display_name="Оля", household_name="Сім'я"
    )

    assert one.household_id == two.household_id
    assert await session.scalar(select(func.count()).select_from(Member)) == 2


async def test_existing_member_is_reused_and_display_name_refreshed(session):
    created = await resolve_member(
        session, telegram_id=111, display_name="Сергій", household_name="Сім'я"
    )
    again = await resolve_member(
        session, telegram_id=111, display_name="Serhii", household_name="Сім'я"
    )

    assert again.id == created.id
    assert again.display_name == "Serhii"


async def test_list_members_is_ordered_by_id(session):
    await resolve_member(session, telegram_id=222, display_name="Оля", household_name="Сім'я")
    await resolve_member(session, telegram_id=111, display_name="Сергій", household_name="Сім'я")

    household = await get_or_create_household(session, "Сім'я")
    assert [m.display_name for m in await list_members(session, household.id)] == ["Оля", "Сергій"]
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_access.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.services.access'`

- [ ] **Step 3: Реалізувати сервіс**

`tg-bot/src/budget_bot/services/access.py`:

```python
"""Household bootstrap and Telegram-user → Member resolution.

The MVP has exactly one household; it is created lazily on the first update
from a whitelisted user, together with the default category list.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Household, Member
from budget_bot.services.categories import ensure_default_categories


async def get_or_create_household(session: AsyncSession, name: str) -> Household:
    household = await session.scalar(select(Household).order_by(Household.id).limit(1))
    if household is not None:
        return household

    household = Household(name=name)
    session.add(household)
    await session.flush()
    await ensure_default_categories(session, household.id)
    return household


async def resolve_member(
    session: AsyncSession, *, telegram_id: int, display_name: str, household_name: str
) -> Member:
    household = await get_or_create_household(session, household_name)
    member = await session.scalar(select(Member).where(Member.telegram_id == telegram_id))

    if member is None:
        member = Member(
            household_id=household.id, telegram_id=telegram_id, display_name=display_name
        )
        session.add(member)
        await session.flush()
        return member

    if display_name and member.display_name != display_name:
        member.display_name = display_name
        await session.flush()
    return member


async def list_members(session: AsyncSession, household_id: int) -> list[Member]:
    result = await session.scalars(
        select(Member).where(Member.household_id == household_id).order_by(Member.id)
    )
    return list(result)
```

- [ ] **Step 4: Додати фікстури `member` і `category` в `conftest.py`**

Додати в кінець `tg-bot/tests/conftest.py`:

```python
from budget_bot.models import Category, Member
from budget_bot.services.categories import ensure_default_categories, list_categories


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
```

- [ ] **Step 5: Запустити всі тести — мають пройти**

Run: `cd tg-bot && .venv/bin/pytest -v`
Expected: усі passed

- [ ] **Step 6: Коміт**

```bash
git add tg-bot/src/budget_bot/services/access.py tg-bot/tests
git commit -m "feat: add household and member bootstrap service"
```

---

### Task 6: Expenses service — create, read, filter

**Files:**
- Create: `tg-bot/src/budget_bot/services/expenses.py`
- Test: `tg-bot/tests/test_services_expenses.py`

**Interfaces:**
- Consumes: `budget_bot.models.Expense`, `budget_bot.periods.PeriodRange`, `budget_bot.clock.utcnow`.
- Produces: `budget_bot.services.expenses` з
  `ExpenseFilters(period: PeriodRange | None = None, category_id: int | None = None, member_id: int | None = None, limit: int = 10)` (frozen dataclass),
  `create_expense(session, *, household_id: int, member_id: int, category_id: int, amount: int, description: str | None = None, created_at: datetime | None = None) -> Expense`,
  `get_expense(session, household_id: int, expense_id: int) -> Expense | None`,
  `list_expenses(session, household_id: int, filters: ExpenseFilters | None = None) -> list[Expense]`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_services_expenses.py`:

```python
from datetime import datetime

from budget_bot.clock import utcnow
from budget_bot.periods import Period, period_range
from budget_bot.services.expenses import ExpenseFilters, create_expense, get_expense, list_expenses

NOW = datetime(2026, 9, 9, 9, 0)  # Wednesday 12:00 Kyiv


async def add(session, household, member, category, *, amount, when, description=None):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        description=description,
        created_at=when,
    )


async def test_create_persists_all_fields(session, household, member, category):
    expense = await add(
        session, household, member, category, amount=250, when=NOW, description="кава"
    )

    assert expense.id is not None
    assert expense.amount == 250
    assert expense.description == "кава"
    assert expense.created_at == NOW
    assert expense.member_id == member.id
    assert expense.updated_at is None


async def test_create_defaults_created_at_to_now(session, household, member, category):
    before = utcnow()
    expense = await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=100,
    )
    assert expense.created_at >= before.replace(microsecond=0)
    assert expense.created_at.tzinfo is None


async def test_list_returns_newest_first_and_respects_limit(
    session, household, member, category
):
    await add(session, household, member, category, amount=1, when=datetime(2026, 9, 1, 9, 0))
    await add(session, household, member, category, amount=2, when=datetime(2026, 9, 2, 9, 0))
    await add(session, household, member, category, amount=3, when=datetime(2026, 9, 3, 9, 0))

    result = await list_expenses(session, household.id, ExpenseFilters(limit=2))
    assert [e.amount for e in result] == [3, 2]


async def test_period_filter_is_half_open(session, household, member, category):
    week = period_range(Period.WEEK, NOW)  # 07.09–13.09 Kyiv
    await add(session, household, member, category, amount=10, when=week.start)
    await add(session, household, member, category, amount=20, when=week.end)

    result = await list_expenses(session, household.id, ExpenseFilters(period=week))
    assert [e.amount for e in result] == [10]


async def test_filters_by_category(session, household, member, category):
    from budget_bot.services.categories import add_category

    other = await add_category(session, household.id, "Кава")
    await add(session, household, member, category, amount=10, when=NOW)
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=other.id,
        amount=20,
        created_at=NOW,
    )

    result = await list_expenses(session, household.id, ExpenseFilters(category_id=other.id))
    assert [e.amount for e in result] == [20]


async def test_filters_by_author(session, household, member, partner, category):
    await add(session, household, member, category, amount=10, when=NOW)
    await add(session, household, partner, category, amount=20, when=NOW)

    result = await list_expenses(session, household.id, ExpenseFilters(member_id=partner.id))
    assert [e.amount for e in result] == [20]
    assert result[0].author.display_name == "Оля"


async def test_empty_result_is_an_empty_list(session, household, member, category):
    result = await list_expenses(session, household.id, ExpenseFilters(member_id=member.id))
    assert result == []


async def test_get_expense_is_scoped_to_household(session, household, member, category):
    expense = await add(session, household, member, category, amount=10, when=NOW)

    assert await get_expense(session, household.id, expense.id) is not None
    assert await get_expense(session, household.id + 1, expense.id) is None
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_expenses.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.services.expenses'`

- [ ] **Step 3: Реалізувати сервіс**

`tg-bot/src/budget_bot/services/expenses.py`:

```python
"""Expense persistence and querying."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.clock import utcnow
from budget_bot.models import Expense
from budget_bot.periods import PeriodRange


@dataclass(frozen=True)
class ExpenseFilters:
    period: PeriodRange | None = None
    category_id: int | None = None
    member_id: int | None = None
    limit: int = 10


async def create_expense(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    category_id: int,
    amount: int,
    description: str | None = None,
    created_at: datetime | None = None,
) -> Expense:
    expense = Expense(
        household_id=household_id,
        member_id=member_id,
        category_id=category_id,
        amount=amount,
        description=description,
        created_at=created_at or utcnow(),
    )
    session.add(expense)
    await session.flush()
    await session.refresh(expense)
    return expense


async def get_expense(
    session: AsyncSession, household_id: int, expense_id: int
) -> Expense | None:
    return await session.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.household_id == household_id)
    )


async def list_expenses(
    session: AsyncSession, household_id: int, filters: ExpenseFilters | None = None
) -> list[Expense]:
    filters = filters or ExpenseFilters()
    query = select(Expense).where(Expense.household_id == household_id)

    if filters.period is not None:
        query = query.where(
            Expense.created_at >= filters.period.start,
            Expense.created_at < filters.period.end,
        )
    if filters.category_id is not None:
        query = query.where(Expense.category_id == filters.category_id)
    if filters.member_id is not None:
        query = query.where(Expense.member_id == filters.member_id)

    query = query.order_by(Expense.created_at.desc(), Expense.id.desc()).limit(filters.limit)
    return list(await session.scalars(query))
```

- [ ] **Step 4: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_expenses.py -v`
Expected: усі passed

- [ ] **Step 5: Коміт**

```bash
git add tg-bot/src/budget_bot/services/expenses.py tg-bot/tests/test_services_expenses.py
git commit -m "feat: add expense creation and filtered listing"
```

---

### Task 7: Expenses service — update and delete

**Files:**
- Modify: `tg-bot/src/budget_bot/services/expenses.py`
- Modify: `tg-bot/tests/test_services_expenses.py`

**Interfaces:**
- Consumes: усе з Task 6.
- Produces: у `budget_bot.services.expenses` додаються
  `UNSET: object` (sentinel, щоб відрізнити «не міняти опис» від «стерти опис»),
  `update_expense(session, expense: Expense, *, editor_id: int, amount: int | None = None, category_id: int | None = None, description: str | None | object = UNSET) -> Expense`,
  `delete_expense(session, expense: Expense) -> None`.

- [ ] **Step 1: Дописати падаючі тести**

Додати в кінець `tg-bot/tests/test_services_expenses.py`:

```python
from budget_bot.services.expenses import UNSET, delete_expense, update_expense


async def test_edit_by_partner_keeps_original_author(
    session, household, member, partner, category
):
    expense = await add(session, household, member, category, amount=250, when=NOW)

    updated = await update_expense(session, expense, editor_id=partner.id, amount=300)

    assert updated.amount == 300
    assert updated.member_id == member.id
    assert updated.author.display_name == "Сергій"
    assert updated.updated_by_id == partner.id
    assert updated.updated_at is not None


async def test_edit_can_change_category_and_description(
    session, household, member, category
):
    from budget_bot.services.categories import add_category

    other = await add_category(session, household.id, "Кава")
    expense = await add(session, household, member, category, amount=250, when=NOW, description="a")

    updated = await update_expense(
        session, expense, editor_id=member.id, category_id=other.id, description="b"
    )

    assert updated.category.name == "Кава"
    assert updated.description == "b"


async def test_description_can_be_cleared_but_is_kept_when_unset(
    session, household, member, category
):
    expense = await add(session, household, member, category, amount=1, when=NOW, description="a")

    await update_expense(session, expense, editor_id=member.id, amount=2, description=UNSET)
    assert expense.description == "a"

    await update_expense(session, expense, editor_id=member.id, description=None)
    assert expense.description is None


async def test_delete_removes_expense_from_listings(session, household, member, category):
    expense = await add(session, household, member, category, amount=10, when=NOW)

    await delete_expense(session, expense)

    assert await get_expense(session, household.id, expense.id) is None
    assert await list_expenses(session, household.id) == []
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_expenses.py -v`
Expected: FAIL — `ImportError: cannot import name 'UNSET'`

- [ ] **Step 3: Дописати реалізацію**

Додати в кінець `tg-bot/src/budget_bot/services/expenses.py`:

```python
class _Unset:
    """Sentinel type: distinguishes 'leave description alone' from 'clear it'."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNSET"


UNSET = _Unset()


async def update_expense(
    session: AsyncSession,
    expense: Expense,
    *,
    editor_id: int,
    amount: int | None = None,
    category_id: int | None = None,
    description: str | None | _Unset = UNSET,
) -> Expense:
    """Apply an edit. The author (member_id) is never reassigned."""
    if amount is not None:
        expense.amount = amount
    if category_id is not None:
        expense.category_id = category_id
    if not isinstance(description, _Unset):
        expense.description = description

    expense.updated_by_id = editor_id
    expense.updated_at = utcnow()

    await session.flush()
    await session.refresh(expense)
    return expense


async def delete_expense(session: AsyncSession, expense: Expense) -> None:
    await session.delete(expense)
    await session.flush()
```

- [ ] **Step 4: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_expenses.py -v`
Expected: усі passed

- [ ] **Step 5: Коміт**

```bash
git add tg-bot/src/budget_bot/services/expenses.py tg-bot/tests/test_services_expenses.py
git commit -m "feat: add expense editing and deletion with editor tracking"
```

---

### Task 8: Reports service

**Files:**
- Create: `tg-bot/src/budget_bot/services/reports.py`
- Test: `tg-bot/tests/test_services_reports.py`

**Interfaces:**
- Consumes: `budget_bot.models.{Expense, Category, Member}`, `budget_bot.periods.PeriodRange`.
- Produces: `budget_bot.services.reports` з
  `CategoryTotal(name: str, amount: int, share: float)`,
  `MemberTotal(display_name: str, amount: int)`,
  `Report(period_label: str, total: int, by_category: list[CategoryTotal], by_member: list[MemberTotal])`,
  `build_report(session, household_id: int, period: PeriodRange) -> Report`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_services_reports.py`:

```python
from datetime import datetime

from budget_bot.periods import Period, period_range
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense
from budget_bot.services.reports import build_report

NOW = datetime(2026, 9, 9, 9, 0)  # Wednesday 12:00 Kyiv
WEEK = period_range(Period.WEEK, NOW)


async def add(session, household, member, category, amount, when=NOW):
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        created_at=when,
    )


async def test_empty_period_reports_zero(session, household, member, category):
    report = await build_report(session, household.id, WEEK)

    assert report.total == 0
    assert report.by_category == []
    assert report.by_member == []
    assert report.period_label == WEEK.label


async def test_totals_and_shares(session, household, member, partner, category):
    coffee = await add_category(session, household.id, "Кава")
    await add(session, household, member, category, 600)
    await add(session, household, partner, category, 200)
    await add(session, household, partner, coffee, 200)

    report = await build_report(session, household.id, WEEK)

    assert report.total == 1000
    assert [(c.name, c.amount, c.share) for c in report.by_category] == [
        ("Їжа", 800, 80.0),
        ("Кава", 200, 20.0),
    ]
    assert [(m.display_name, m.amount) for m in report.by_member] == [
        ("Сергій", 600),
        ("Оля", 400),
    ]


async def test_expenses_outside_the_period_are_excluded(
    session, household, member, category
):
    await add(session, household, member, category, 100, when=WEEK.start)
    await add(session, household, member, category, 999, when=WEEK.end)

    report = await build_report(session, household.id, WEEK)

    assert report.total == 100


async def test_categories_are_sorted_by_amount_desc(session, household, member, category):
    small = await add_category(session, household.id, "Мале")
    big = await add_category(session, household.id, "Велике")
    await add(session, household, member, small, 10)
    await add(session, household, member, big, 90)

    report = await build_report(session, household.id, WEEK)

    assert [c.name for c in report.by_category] == ["Велике", "Мале"]
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_reports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.services.reports'`

- [ ] **Step 3: Реалізувати сервіс**

`tg-bot/src/budget_bot/services/reports.py`:

```python
"""Aggregated spending reports for a period."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Category, Expense, Member
from budget_bot.periods import PeriodRange


@dataclass(frozen=True)
class CategoryTotal:
    name: str
    amount: int
    share: float  # percent of the period total, one decimal


@dataclass(frozen=True)
class MemberTotal:
    display_name: str
    amount: int


@dataclass(frozen=True)
class Report:
    period_label: str
    total: int
    by_category: list[CategoryTotal]
    by_member: list[MemberTotal]


async def build_report(
    session: AsyncSession, household_id: int, period: PeriodRange
) -> Report:
    scope = (
        Expense.household_id == household_id,
        Expense.created_at >= period.start,
        Expense.created_at < period.end,
    )

    total = await session.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(*scope)
    )
    if not total:
        return Report(period_label=period.label, total=0, by_category=[], by_member=[])

    category_rows = await session.execute(
        select(Category.name, func.sum(Expense.amount))
        .join(Category, Category.id == Expense.category_id)
        .where(*scope)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(Expense.amount).desc(), Category.name)
    )
    member_rows = await session.execute(
        select(Member.display_name, func.sum(Expense.amount))
        .join(Member, Member.id == Expense.member_id)
        .where(*scope)
        .group_by(Member.id, Member.display_name)
        .order_by(func.sum(Expense.amount).desc(), Member.display_name)
    )

    return Report(
        period_label=period.label,
        total=int(total),
        by_category=[
            CategoryTotal(name=name, amount=int(amount), share=round(amount * 100 / total, 1))
            for name, amount in category_rows.all()
        ],
        by_member=[
            MemberTotal(display_name=name, amount=int(amount))
            for name, amount in member_rows.all()
        ],
    )
```

- [ ] **Step 4: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_services_reports.py -v`
Expected: усі passed

- [ ] **Step 5: Коміт**

```bash
git add tg-bot/src/budget_bot/services/reports.py tg-bot/tests/test_services_reports.py
git commit -m "feat: add period report aggregation"
```

---

### Task 9: Message formatting

**Files:**
- Create: `tg-bot/src/budget_bot/formatting.py`
- Test: `tg-bot/tests/test_formatting.py`

**Interfaces:**
- Consumes: `budget_bot.amounts.format_amount`, `budget_bot.periods.{format_date_short, format_datetime}`, `budget_bot.services.reports.Report`.
- Produces: `budget_bot.formatting` з
  `format_expense_line(expense, index: int | None = None) -> str`,
  `format_expense_list(expenses, header: str, empty_message: str) -> str`,
  `format_expense_card(expense) -> str`,
  `format_saved_expense(expense) -> str`,
  `format_report(report: Report) -> str`.
  Усі повертають HTML (`parse_mode=HTML`), увесь користувацький текст екранований.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_formatting.py`:

```python
from datetime import datetime

from budget_bot.formatting import (
    format_expense_card,
    format_expense_line,
    format_expense_list,
    format_report,
    format_saved_expense,
)
from budget_bot.services.expenses import create_expense, update_expense
from budget_bot.services.reports import CategoryTotal, MemberTotal, Report

NOW = datetime(2026, 9, 7, 9, 0)  # 12:00 Kyiv


async def make(session, household, member, category, **kwargs):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=kwargs.get("amount", 250),
        description=kwargs.get("description"),
        created_at=NOW,
    )


async def test_expense_line(session, household, member, category):
    expense = await make(session, household, member, category, description="кава")

    assert format_expense_line(expense) == "07.09 · 250\u00a0₴ · Їжа · Сергій — кава"


async def test_expense_line_without_description_and_with_index(
    session, household, member, category
):
    expense = await make(session, household, member, category)

    assert format_expense_line(expense, index=3) == "<b>3.</b> 07.09 · 250\u00a0₴ · Їжа · Сергій"


async def test_user_text_is_html_escaped(session, household, member, category):
    expense = await make(session, household, member, category, description="<b>hack</b>")

    assert "&lt;b&gt;hack&lt;/b&gt;" in format_expense_line(expense)
    assert "<b>hack</b>" not in format_expense_line(expense)


async def test_empty_list_uses_the_empty_message(session):
    assert format_expense_list([], "Останні витрати", "Витрат не знайдено") == (
        "Витрат не знайдено"
    )


async def test_list_is_numbered_from_one(session, household, member, category):
    first = await make(session, household, member, category, amount=1)
    second = await make(session, household, member, category, amount=2)

    text = format_expense_list([first, second], "Останні витрати", "порожньо")

    assert text.startswith("<b>Останні витрати</b>")
    assert "<b>1.</b>" in text and "<b>2.</b>" in text


async def test_card_shows_editor_when_edited(session, household, member, partner, category):
    expense = await make(session, household, member, category, description="кава")
    await update_expense(session, expense, editor_id=partner.id, amount=300)

    card = format_expense_card(expense)

    assert f"Витрата #{expense.id}" in card
    assert "300\u00a0₴" in card
    assert "Автор: Сергій" in card
    assert "Змінив(ла): Оля" in card


async def test_card_without_edit_has_no_editor_line(session, household, member, category):
    card = format_expense_card(await make(session, household, member, category))

    assert "Змінив(ла)" not in card


async def test_saved_expense_confirmation(session, household, member, category):
    expense = await make(session, household, member, category)

    assert format_saved_expense(expense).startswith("✅ Записано:")


def test_report_with_data():
    report = Report(
        period_label="поточний тиждень (07.09–13.09.2026)",
        total=1000,
        by_category=[CategoryTotal("Їжа", 800, 80.0), CategoryTotal("Кава", 200, 20.0)],
        by_member=[MemberTotal("Сергій", 600), MemberTotal("Оля", 400)],
    )

    text = format_report(report)

    assert "поточний тиждень (07.09–13.09.2026)" in text
    assert "1\u00a0000\u00a0₴" in text
    assert "• Їжа — 800\u00a0₴ (80.0%)" in text
    assert "• Сергій — 600\u00a0₴" in text


def test_empty_report_says_so_without_error():
    report = Report(period_label="поточний рік (2026)", total=0, by_category=[], by_member=[])

    text = format_report(report)

    assert "Витрат за цей період не знайдено" in text
    assert "%" not in text
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_formatting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.formatting'`

- [ ] **Step 3: Реалізувати `formatting.py`**

```python
"""Rendering of user-facing messages. Output is Telegram HTML."""

from collections.abc import Sequence
from html import escape

from budget_bot.amounts import format_amount
from budget_bot.models import Expense
from budget_bot.periods import format_date_short, format_datetime
from budget_bot.services.reports import Report


def format_expense_line(expense: Expense, index: int | None = None) -> str:
    parts = [
        format_date_short(expense.created_at),
        format_amount(expense.amount),
        escape(expense.category.name),
        escape(expense.author.display_name),
    ]
    line = " · ".join(parts)
    if expense.description:
        line += f" — {escape(expense.description)}"
    if index is not None:
        line = f"<b>{index}.</b> {line}"
    return line


def format_expense_list(
    expenses: Sequence[Expense], header: str, empty_message: str
) -> str:
    if not expenses:
        return empty_message
    lines = [f"<b>{escape(header)}</b>", ""]
    lines.extend(
        format_expense_line(expense, index=number)
        for number, expense in enumerate(expenses, start=1)
    )
    return "\n".join(lines)


def format_expense_card(expense: Expense) -> str:
    lines = [
        f"🧾 <b>Витрата #{expense.id}</b>",
        f"Сума: <b>{format_amount(expense.amount)}</b>",
        f"Категорія: {escape(expense.category.name)}",
        f"Автор: {escape(expense.author.display_name)}",
        f"Дата: {format_datetime(expense.created_at)}",
    ]
    if expense.description:
        lines.append(f"Опис: {escape(expense.description)}")
    if expense.updated_at is not None and expense.updated_by is not None:
        lines.append(
            "✏️ Змінив(ла): "
            f"{escape(expense.updated_by.display_name)}, {format_datetime(expense.updated_at)}"
        )
    return "\n".join(lines)


def format_saved_expense(expense: Expense) -> str:
    return f"✅ Записано: {format_expense_line(expense)}"


def format_report(report: Report) -> str:
    header = f"📊 <b>Звіт — {escape(report.period_label)}</b>"
    if report.total == 0:
        return f"{header}\n\nВитрат за цей період не знайдено."

    lines = [header, f"Разом: <b>{format_amount(report.total)}</b>", "", "<b>За категоріями:</b>"]
    lines.extend(
        f"• {escape(item.name)} — {format_amount(item.amount)} ({item.share:.1f}%)"
        for item in report.by_category
    )
    lines.extend(["", "<b>За учасниками:</b>"])
    lines.extend(
        f"• {escape(item.display_name)} — {format_amount(item.amount)}"
        for item in report.by_member
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_formatting.py -v`
Expected: усі passed

- [ ] **Step 5: Прогнати весь набір і лінт**

Run: `cd tg-bot && .venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/black --check .`
Expected: усе зелене

- [ ] **Step 6: Коміт**

```bash
git add tg-bot/src/budget_bot/formatting.py tg-bot/tests/test_formatting.py
git commit -m "feat: add message formatting for expenses and reports"
```

---
### Task 10: Bot skeleton — access middleware, main menu, /start

**Files:**
- Create: `tg-bot/src/budget_bot/bot/__init__.py`
- Create: `tg-bot/src/budget_bot/bot/callbacks.py`
- Create: `tg-bot/src/budget_bot/bot/keyboards.py`
- Create: `tg-bot/src/budget_bot/bot/middlewares.py`
- Create: `tg-bot/src/budget_bot/bot/handlers/__init__.py`
- Create: `tg-bot/src/budget_bot/bot/handlers/common.py`
- Create: `tg-bot/src/budget_bot/__main__.py`
- Modify: `tg-bot/tests/conftest.py` (додати `FakeMessage`, `FakeCallback`, фікстуру `state`)
- Test: `tg-bot/tests/test_middlewares.py`, `tg-bot/tests/test_handlers_common.py`

**Interfaces:**
- Consumes: `budget_bot.services.access.resolve_member`, `budget_bot.config.Settings`, `budget_bot.db.*`.
- Produces:
  - `budget_bot.bot.callbacks`: `CategoryCb(action: str, category_id: int)` prefix `cat`; `ExpenseCb(action: str, expense_id: int)` prefix `exp`; `EditFieldCb(field: str, expense_id: int)` prefix `edit`; `ReportCb(period: str)` prefix `rep`; `FilterCb(step: str, value: str)` prefix `flt`; `FlowCb(action: str)` prefix `flow`.
  - `budget_bot.bot.keyboards`: константи `BTN_ADD, BTN_LIST, BTN_REPORT, BTN_FILTER, BTN_CATEGORIES`; `main_menu() -> ReplyKeyboardMarkup`; `cancel_keyboard() -> InlineKeyboardMarkup`.
  - `budget_bot.bot.middlewares`: `DENIED_TEXT: str`, `DbSessionMiddleware(session_factory)`, `AccessMiddleware(allowed_ids: frozenset[int], household_name: str)`.
  - `budget_bot.bot.handlers.build_router() -> Router`.
  - `budget_bot.bot.handlers.common`: `router`, `HELP_TEXT`, `cmd_start(message, member)`, `cmd_help(message)`, `cmd_cancel(message, state)`, `cb_cancel(callback, state)`.
  - Дані, які middleware кладе в `data` і які aiogram впорскує в хендлери за іменем аргументу: `session: AsyncSession`, `member: Member`, `settings: Settings`.

- [ ] **Step 1: Додати тестові фейки в `conftest.py`**

Додати в кінець `tg-bot/tests/conftest.py`:

```python
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage


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
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=111)
    )
```

- [ ] **Step 2: Написати падаючі тести middleware**

`tg-bot/tests/test_middlewares.py`:

```python
from sqlalchemy import func, select

from budget_bot.bot.middlewares import DENIED_TEXT, AccessMiddleware, DbSessionMiddleware
from budget_bot.db import create_engine, create_session_factory
from budget_bot.models import Base, Household
from tests.conftest import FakeCallback, FakeMessage


async def test_access_middleware_injects_member_and_calls_handler(session):
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")
    captured: dict = {}

    async def handler(event, data):
        captured.update(data)
        return "handled"

    result = await middleware(handler, FakeMessage(text="/start"), {"session": session})

    assert result == "handled"
    assert captured["member"].telegram_id == 111
    assert captured["member"].display_name == "Сергій"


async def test_access_middleware_blocks_unknown_telegram_id(session):
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")
    calls = []

    async def handler(event, data):
        calls.append(event)

    message = FakeMessage(text="/start", user_id=999)
    result = await middleware(handler, message, {"session": session})

    assert result is None
    assert calls == []
    assert message.last_reply == DENIED_TEXT
    assert await session.scalar(select(func.count()).select_from(Household)) == 0


async def test_access_middleware_blocks_unknown_user_on_callback(session):
    middleware = AccessMiddleware(frozenset({111}), "Сім'я")

    async def handler(event, data):
        raise AssertionError("handler must not be called")

    callback = FakeCallback(user_id=999)
    await middleware(handler, callback, {"session": session})

    assert callback.answers[-1][0] == DENIED_TEXT


async def test_db_session_middleware_commits_on_success(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)

    async def handler(event, data):
        data["session"].add(Household(name="Сім'я"))

    await DbSessionMiddleware(factory)(handler, FakeMessage(), {})

    async with factory() as check:
        assert await check.scalar(select(func.count()).select_from(Household)) == 1
    await engine.dispose()


async def test_db_session_middleware_rolls_back_on_error(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)

    async def handler(event, data):
        data["session"].add(Household(name="Сім'я"))
        raise RuntimeError("boom")

    try:
        await DbSessionMiddleware(factory)(handler, FakeMessage(), {})
    except RuntimeError:
        pass

    async with factory() as check:
        assert await check.scalar(select(func.count()).select_from(Household)) == 0
    await engine.dispose()
```

- [ ] **Step 3: Написати падаючі тести /start**

`tg-bot/tests/test_handlers_common.py`:

```python
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
```

- [ ] **Step 4: Запустити — мають впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_middlewares.py tests/test_handlers_common.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot'`

- [ ] **Step 5: Створити пакет `bot` і callback-фабрики**

```bash
mkdir -p tg-bot/src/budget_bot/bot/handlers
touch tg-bot/src/budget_bot/bot/__init__.py
```

`tg-bot/src/budget_bot/bot/callbacks.py`:

```python
"""Typed callback-data factories shared by keyboards and handlers."""

from aiogram.filters.callback_data import CallbackData


class CategoryCb(CallbackData, prefix="cat"):
    action: str  # "pick" | "filter"
    category_id: int


class ExpenseCb(CallbackData, prefix="exp"):
    action: str  # "view" | "edit" | "delete" | "delete_yes" | "back"
    expense_id: int


class EditFieldCb(CallbackData, prefix="edit"):
    field: str  # "amount" | "category" | "description"
    expense_id: int


class ReportCb(CallbackData, prefix="rep"):
    period: str  # a budget_bot.periods.Period value


class FilterCb(CallbackData, prefix="flt"):
    step: str  # "period" | "category" | "member" | "apply"
    value: str


class FlowCb(CallbackData, prefix="flow"):
    action: str  # "cancel" | "skip" | "save" | "add_category"
```

- [ ] **Step 6: Створити клавіатури**

`tg-bot/src/budget_bot/bot/keyboards.py`:

```python
"""Keyboard builders. Button labels are constants so handlers can match on them."""

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from budget_bot.bot.callbacks import FlowCb

BTN_ADD = "➕ Витрата"
BTN_LIST = "📋 Список"
BTN_REPORT = "📊 Звіт"
BTN_FILTER = "🔎 Фільтр"
BTN_CATEGORIES = "🏷 Категорії"


def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN_ADD)
    builder.button(text=BTN_LIST)
    builder.button(text=BTN_REPORT)
    builder.button(text=BTN_FILTER)
    builder.button(text=BTN_CATEGORIES)
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    return builder.as_markup()
```

> У наступних задачах цей файл дописується новими білдерами. Кожен раз додавайте
> нові імпорти до блоку імпортів угорі файлу — `ruff` (правило `I`) вимагає їх там.

- [ ] **Step 7: Створити middleware**

`tg-bot/src/budget_bot/bot/middlewares.py`:

```python
"""Outer middlewares: one DB session per update, whitelist enforcement."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from budget_bot.services.access import resolve_member

DENIED_TEXT = "⛔️ Доступ заборонено."


class DbSessionMiddleware(BaseMiddleware):
    """Opens one session per update and commits it if the handler succeeded."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result


class AccessMiddleware(BaseMiddleware):
    """Rejects updates from Telegram IDs outside the whitelist.

    Runs on messages and callback queries only, so ``event.from_user`` is
    always present for allowed traffic.
    """

    def __init__(self, allowed_ids: frozenset[int], household_name: str) -> None:
        self.allowed_ids = allowed_ids
        self.household_name = household_name

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or user.id not in self.allowed_ids:
            await self._deny(event)
            return None

        data["member"] = await resolve_member(
            data["session"],
            telegram_id=user.id,
            display_name=user.first_name or str(user.id),
            household_name=self.household_name,
        )
        return await handler(event, data)

    @staticmethod
    async def _deny(event: TelegramObject) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(DENIED_TEXT, show_alert=True)
            return
        await event.answer(DENIED_TEXT)
```

- [ ] **Step 8: Створити `common.py` і `build_router`**

`tg-bot/src/budget_bot/bot/handlers/common.py`:

```python
"""/start, /help and the global /cancel escape hatch."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from budget_bot.bot.callbacks import FlowCb
from budget_bot.bot.keyboards import main_menu
from budget_bot.models import Member

router = Router(name="common")

HELP_TEXT = (
    "Що я вмію:\n"
    "➕ /add — додати витрату\n"
    "📋 /list — останні витрати\n"
    "🔎 /filter — фільтр за періодом, категорією, автором\n"
    "📊 /report — звіт за тиждень / місяць / рік\n"
    "🏷 /categories — список категорій і додавання власної\n"
    "❌ /cancel — перервати поточний діалог\n\n"
    "Суми — у гривнях, цілими числами. Усі записи спільні для родини."
)


@router.message(CommandStart())
async def cmd_start(message: Message, member: Member) -> None:
    await message.answer(
        f"👋 Привіт, {member.display_name}! Це бот сімейного бюджету.\n\n{HELP_TEXT}",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    had_dialog = await state.get_state() is not None
    await state.clear()
    text = "❌ Скасовано." if had_dialog else "Немає активного діалогу."
    await message.answer(text, reply_markup=main_menu())


@router.callback_query(FlowCb.filter(F.action == "cancel"), StateFilter("*"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Скасовано.")
    await callback.answer()
```

`tg-bot/src/budget_bot/bot/handlers/__init__.py`:

```python
"""Router composition. Order matters: /cancel must win over FSM state handlers."""

from aiogram import Router

from budget_bot.bot.handlers import common


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(common.router)
    return router
```

- [ ] **Step 9: Створити `__main__.py`**

`tg-bot/src/budget_bot/__main__.py`:

```python
"""Composition root: wires config, database, middlewares and handlers."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from budget_bot.bot.handlers import build_router
from budget_bot.bot.middlewares import AccessMiddleware, DbSessionMiddleware
from budget_bot.config import Settings
from budget_bot.db import create_engine, create_session_factory

BOT_COMMANDS = [
    BotCommand(command="add", description="Додати витрату"),
    BotCommand(command="list", description="Останні витрати"),
    BotCommand(command="filter", description="Фільтр витрат"),
    BotCommand(command="report", description="Звіт за період"),
    BotCommand(command="categories", description="Категорії"),
    BotCommand(command="cancel", description="Перервати діалог"),
]


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # MemoryStorage is enough for two users: a restart only drops in-flight
    # dialogs, never saved data.
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["settings"] = settings

    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    access = AccessMiddleware(settings.allowed_telegram_ids, settings.household_name)
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)

    dispatcher.include_router(build_router())

    await bot.set_my_commands(BOT_COMMANDS)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 10: Запустити тести — мають пройти**

Run: `cd tg-bot && .venv/bin/pytest -v`
Expected: усі passed

- [ ] **Step 11: Коміт**

```bash
git add tg-bot/src/budget_bot/bot tg-bot/src/budget_bot/__main__.py tg-bot/tests
git commit -m "feat: add bot skeleton with whitelist middleware, main menu and /start"
```

---

### Task 11: Categories handlers

**Files:**
- Create: `tg-bot/src/budget_bot/bot/handlers/categories.py`
- Modify: `tg-bot/src/budget_bot/bot/handlers/__init__.py`
- Modify: `tg-bot/src/budget_bot/bot/keyboards.py` (додати `add_category_keyboard`)
- Test: `tg-bot/tests/test_handlers_categories.py`

**Interfaces:**
- Consumes: `budget_bot.services.categories.{list_categories, add_category, DuplicateCategoryError, CategoryNameError}`, `budget_bot.bot.keyboards.{BTN_CATEGORIES, cancel_keyboard, main_menu}`, `FlowCb`.
- Produces: `budget_bot.bot.handlers.categories` з `router`, `AddCategory(StatesGroup)` зі станом `name`, `cmd_categories(message, session, member)`, `cb_start_add_category(callback, state)`, `enter_category_name(message, state, session, member)`; `keyboards.add_category_keyboard() -> InlineKeyboardMarkup`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_handlers_categories.py`:

```python
from budget_bot.bot.handlers.categories import (
    AddCategory,
    cb_start_add_category,
    cmd_categories,
    enter_category_name,
)
from budget_bot.services.categories import list_categories
from tests.conftest import FakeCallback, FakeMessage


async def test_categories_command_lists_defaults(session, member, category):
    message = FakeMessage(text="/categories")

    await cmd_categories(message, session=session, member=member)

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
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_categories.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot.handlers.categories'`

- [ ] **Step 3: Додати клавіатуру**

Додати в `tg-bot/src/budget_bot/bot/keyboards.py`:

```python
def add_category_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати категорію", callback_data=FlowCb(action="add_category"))
    return builder.as_markup()
```

- [ ] **Step 4: Реалізувати хендлери**

`tg-bot/src/budget_bot/bot/handlers/categories.py`:

```python
"""/categories: show the shared list and add a custom category."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import FlowCb
from budget_bot.bot.keyboards import BTN_CATEGORIES, add_category_keyboard, cancel_keyboard
from budget_bot.models import Member
from budget_bot.services.categories import (
    CategoryNameError,
    DuplicateCategoryError,
    add_category,
    list_categories,
)

router = Router(name="categories")


class AddCategory(StatesGroup):
    name = State()


@router.message(Command("categories"))
@router.message(F.text == BTN_CATEGORIES)
async def cmd_categories(message: Message, session: AsyncSession, member: Member) -> None:
    categories = await list_categories(session, member.household_id)
    lines = ["<b>🏷 Категорії</b>", ""]
    lines.extend(
        f"• {escape(item.name)}" + (" (власна)" if item.is_custom else "")
        for item in categories
    )
    await message.answer("\n".join(lines), reply_markup=add_category_keyboard())


@router.callback_query(FlowCb.filter(F.action == "add_category"))
async def cb_start_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCategory.name)
    await callback.message.answer(
        "Введіть назву нової категорії:", reply_markup=cancel_keyboard()
    )
    await callback.answer()


@router.message(AddCategory.name)
async def enter_category_name(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        category = await add_category(session, member.household_id, message.text or "")
    except (DuplicateCategoryError, CategoryNameError) as error:
        # Stay in the same state so the user can retype without restarting.
        await message.answer(f"⚠️ {error}", reply_markup=cancel_keyboard())
        return

    await state.clear()
    await message.answer(f"✅ Категорію «{escape(category.name)}» додано.")
```

- [ ] **Step 6: Підключити роутер**

У `tg-bot/src/budget_bot/bot/handlers/__init__.py`:

```python
from budget_bot.bot.handlers import categories, common


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(common.router, categories.router)
    return router
```

- [ ] **Step 7: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_categories.py -v`
Expected: усі passed

- [ ] **Step 8: Коміт**

```bash
git add tg-bot/src/budget_bot/bot tg-bot/tests/test_handlers_categories.py
git commit -m "feat: add /categories listing and custom category dialog"
```

---

### Task 12: Add-expense dialog (/add)

**Files:**
- Create: `tg-bot/src/budget_bot/bot/texts.py`
- Create: `tg-bot/src/budget_bot/bot/handlers/add_expense.py`
- Modify: `tg-bot/src/budget_bot/bot/handlers/__init__.py`
- Modify: `tg-bot/src/budget_bot/bot/keyboards.py` (додати `categories_keyboard`, `description_keyboard`, `confirm_keyboard`)
- Test: `tg-bot/tests/test_handlers_add_expense.py`

**Interfaces:**
- Consumes: `budget_bot.amounts.{parse_amount, AmountError, format_amount}`, `budget_bot.services.categories.{list_categories, get_category}`, `budget_bot.services.expenses.create_expense`, `budget_bot.formatting.format_saved_expense`, `CategoryCb`, `FlowCb`.
- Produces: `budget_bot.bot.texts` зі спільними для хендлерів рядками —
  `MISSING_EXPENSE_TEXT`, `EMPTY_LIST_TEXT`, `EMPTY_RESULT_TEXT`,
  `MAX_DESCRIPTION_LENGTH = 255`, `CLEAR_DESCRIPTION_TOKEN = "-"`;
  `budget_bot.bot.handlers.add_expense` з `router`, `AddExpense(StatesGroup)` зі станами `amount, category, description, confirm`, і хендлерами `start_add(message, state)`, `enter_amount(message, state, session, member)`, `pick_category(callback, callback_data, state, session, member)`, `enter_description(message, state)`, `skip_description(callback, state)`, `save_expense(callback, state, session, member)`; `keyboards.categories_keyboard(categories, action="pick")`, `keyboards.description_keyboard()`, `keyboards.confirm_keyboard()`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_handlers_add_expense.py`:

```python
from budget_bot.bot.callbacks import CategoryCb
from budget_bot.bot.handlers.add_expense import (
    AddExpense,
    enter_amount,
    enter_description,
    pick_category,
    save_expense,
    skip_description,
    start_add,
)
from budget_bot.services.expenses import list_expenses
from tests.conftest import FakeCallback, FakeMessage


async def test_full_flow_saves_expense_with_description(session, member, category, state):
    await start_add(FakeMessage(text="/add"), state=state)
    assert await state.get_state() == AddExpense.amount

    await enter_amount(FakeMessage(text="250"), state=state, session=session, member=member)
    assert await state.get_state() == AddExpense.category

    callback = FakeCallback()
    await pick_category(
        callback,
        callback_data=CategoryCb(action="pick", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    assert await state.get_state() == AddExpense.description

    await enter_description(FakeMessage(text="кава"), state=state)
    assert await state.get_state() == AddExpense.confirm

    confirm = FakeCallback()
    await save_expense(confirm, state=state, session=session, member=member)

    assert await state.get_state() is None
    saved = await list_expenses(session, member.household_id)
    assert len(saved) == 1
    assert saved[0].amount == 250
    assert saved[0].description == "кава"
    assert saved[0].member_id == member.id
    assert "Записано" in confirm.message.last_edit


async def test_description_can_be_skipped(session, member, category, state):
    await state.set_state(AddExpense.category)
    callback = FakeCallback()
    await pick_category(
        callback,
        callback_data=CategoryCb(action="pick", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    await state.update_data(amount=100)

    await skip_description(callback, state=state)
    assert await state.get_state() == AddExpense.confirm

    await save_expense(FakeCallback(), state=state, session=session, member=member)

    saved = await list_expenses(session, member.household_id)
    assert saved[0].description is None


async def test_invalid_amount_keeps_the_state_and_explains(session, member, category, state):
    await state.set_state(AddExpense.amount)
    message = FakeMessage(text="12.5")

    await enter_amount(message, state=state, session=session, member=member)

    assert await state.get_state() == AddExpense.amount
    assert "цілим числом" in message.last_reply
    assert await list_expenses(session, member.household_id) == []


async def test_zero_amount_is_rejected(session, member, category, state):
    await state.set_state(AddExpense.amount)
    message = FakeMessage(text="0")

    await enter_amount(message, state=state, session=session, member=member)

    assert await state.get_state() == AddExpense.amount
    assert "більшою за нуль" in message.last_reply


async def test_unknown_category_is_reported(session, member, category, state):
    await state.set_state(AddExpense.category)
    await state.update_data(amount=100)
    callback = FakeCallback()

    await pick_category(
        callback,
        callback_data=CategoryCb(action="pick", category_id=999),
        state=state,
        session=session,
        member=member,
    )

    assert callback.answers[-1][1] is True  # show_alert
    assert await state.get_state() == AddExpense.category
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_add_expense.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot.handlers.add_expense'`

- [ ] **Step 3: Створити модуль спільних рядків**

`tg-bot/src/budget_bot/bot/texts.py`:

```python
"""User-facing strings shared by more than one handler module."""

MISSING_EXPENSE_TEXT = "Запис не знайдено — можливо, його вже видалили."
EMPTY_LIST_TEXT = "Витрат ще немає. Додайте першу через /add."
EMPTY_RESULT_TEXT = "Витрат за цей період не знайдено."

# Matches the Expense.description column width.
MAX_DESCRIPTION_LENGTH = 255
# Typing this instead of a new description clears the field.
CLEAR_DESCRIPTION_TOKEN = "-"
```

- [ ] **Step 4: Додати клавіатури**

Додати в `tg-bot/src/budget_bot/bot/keyboards.py`:

```python
from collections.abc import Sequence

from budget_bot.bot.callbacks import CategoryCb
from budget_bot.models import Category


def categories_keyboard(
    categories: Sequence[Category], action: str = "pick"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in categories:
        builder.button(
            text=item.name, callback_data=CategoryCb(action=action, category_id=item.id)
        )
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()


def description_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустити", callback_data=FlowCb(action="skip"))
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Зберегти", callback_data=FlowCb(action="save"))
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()
```

- [ ] **Step 5: Реалізувати діалог**

`tg-bot/src/budget_bot/bot/handlers/add_expense.py`:

```python
"""/add: amount → category → optional description → confirmation."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.amounts import AmountError, format_amount, parse_amount
from budget_bot.bot.callbacks import CategoryCb, FlowCb
from budget_bot.bot.keyboards import (
    BTN_ADD,
    cancel_keyboard,
    categories_keyboard,
    confirm_keyboard,
    description_keyboard,
)
from budget_bot.bot.texts import MAX_DESCRIPTION_LENGTH
from budget_bot.formatting import format_saved_expense
from budget_bot.models import Member
from budget_bot.services.categories import get_category, list_categories
from budget_bot.services.expenses import create_expense

router = Router(name="add_expense")


class AddExpense(StatesGroup):
    amount = State()
    category = State()
    description = State()
    confirm = State()


@router.message(Command("add"))
@router.message(F.text == BTN_ADD)
async def start_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddExpense.amount)
    await message.answer(
        "💸 Введіть суму витрати в гривнях (ціле число):", reply_markup=cancel_keyboard()
    )


@router.message(AddExpense.amount)
async def enter_amount(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        amount = parse_amount(message.text or "")
    except AmountError as error:
        await message.answer(f"⚠️ {error}", reply_markup=cancel_keyboard())
        return

    await state.update_data(amount=amount)
    await state.set_state(AddExpense.category)
    categories = await list_categories(session, member.household_id)
    await message.answer("Оберіть категорію:", reply_markup=categories_keyboard(categories))


@router.callback_query(AddExpense.category, CategoryCb.filter(F.action == "pick"))
async def pick_category(
    callback: CallbackQuery,
    callback_data: CategoryCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    category = await get_category(session, member.household_id, callback_data.category_id)
    if category is None:
        await callback.answer("Категорію не знайдено. Оберіть іншу.", show_alert=True)
        return

    await state.update_data(category_id=category.id, category_name=category.name)
    await state.set_state(AddExpense.description)
    await callback.message.answer(
        f"Категорія: <b>{escape(category.name)}</b>\n\nДодайте опис або пропустіть цей крок:",
        reply_markup=description_keyboard(),
    )
    await callback.answer()


@router.message(AddExpense.description)
async def enter_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()[:MAX_DESCRIPTION_LENGTH] or None
    await _ask_confirmation(message, state, description)


@router.callback_query(AddExpense.description, FlowCb.filter(F.action == "skip"))
async def skip_description(callback: CallbackQuery, state: FSMContext) -> None:
    await _ask_confirmation(callback.message, state, None)
    await callback.answer()


async def _ask_confirmation(message: Message, state: FSMContext, description: str | None) -> None:
    data = await state.update_data(description=description)
    await state.set_state(AddExpense.confirm)
    summary = (
        "Перевірте запис:\n"
        f"Сума: <b>{format_amount(data['amount'])}</b>\n"
        f"Категорія: {escape(data['category_name'])}\n"
        f"Опис: {escape(description) if description else '—'}"
    )
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.callback_query(AddExpense.confirm, FlowCb.filter(F.action == "save"))
async def save_expense(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    data = await state.get_data()
    expense = await create_expense(
        session,
        household_id=member.household_id,
        member_id=member.id,
        category_id=data["category_id"],
        amount=data["amount"],
        description=data.get("description"),
    )
    await state.clear()
    await callback.message.edit_text(format_saved_expense(expense))
    await callback.answer()
```

- [ ] **Step 5: Підключити роутер**

У `build_router()` додати `add_expense.router` **після** `common.router`:

```python
from budget_bot.bot.handlers import add_expense, categories, common


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(common.router, add_expense.router, categories.router)
    return router
```

- [ ] **Step 6: Запустити — має пройти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_add_expense.py -v`
Expected: усі passed

- [ ] **Step 7: Коміт**

```bash
git add tg-bot/src/budget_bot/bot tg-bot/tests/test_handlers_add_expense.py
git commit -m "feat: add step-by-step expense creation dialog"
```

---
### Task 13: Expense list and expense card (/list)

**Files:**
- Create: `tg-bot/src/budget_bot/bot/handlers/expense_list.py`
- Modify: `tg-bot/src/budget_bot/bot/handlers/__init__.py`
- Modify: `tg-bot/src/budget_bot/bot/keyboards.py` (додати `expense_index_keyboard`, `expense_card_keyboard`)
- Modify: `tg-bot/tests/conftest.py` (додати фікстуру `settings`)
- Test: `tg-bot/tests/test_handlers_expense_list.py`

**Interfaces:**
- Consumes: `budget_bot.services.expenses.{ExpenseFilters, list_expenses, get_expense}`, `budget_bot.formatting.{format_expense_list, format_expense_card}`, `ExpenseCb`, `Settings.recent_expenses_limit`.
- Produces: `budget_bot.bot.handlers.expense_list` з `router`, `cmd_list(message, session, member, settings)`, `show_expense(callback, callback_data, session, member)`; `keyboards.expense_index_keyboard(expenses) -> InlineKeyboardMarkup`, `keyboards.expense_card_keyboard(expense_id: int) -> InlineKeyboardMarkup`.

- [ ] **Step 1: Додати фікстуру `settings` в `conftest.py`**

```python
from budget_bot.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        TELEGRAM_BOT_TOKEN="123:ABC",
        ALLOWED_TELEGRAM_IDS="111,222",
        RECENT_EXPENSES_LIMIT=10,
    )
```

- [ ] **Step 2: Написати падаючий тест**

`tg-bot/tests/test_handlers_expense_list.py`:

```python
from datetime import datetime

from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.handlers.expense_list import cmd_list, show_expense
from budget_bot.services.expenses import create_expense
from tests.conftest import FakeCallback, FakeMessage

NOW = datetime(2026, 9, 7, 9, 0)


async def make(session, household, member, category, amount, description=None):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        description=description,
        created_at=NOW,
    )


async def test_empty_list_explains_how_to_start(session, member, category, settings):
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings)

    assert "Витрат ще немає" in message.last_reply
    assert message.replies[-1][1].get("reply_markup") is None


async def test_list_shows_records_newest_first_with_index_buttons(
    session, household, member, category, settings
):
    await make(session, household, member, category, 100)
    await make(session, household, member, category, 200, description="кава")
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings)

    text, kwargs = message.replies[-1]
    assert "<b>1.</b>" in text and "<b>2.</b>" in text
    buttons = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["1", "2"]


async def test_list_respects_the_configured_limit(
    session, household, member, category, settings
):
    for amount in range(1, 6):
        await make(session, household, member, category, amount)
    settings.recent_expenses_limit = 3
    message = FakeMessage(text="/list")

    await cmd_list(message, session=session, member=member, settings=settings)

    assert "<b>3.</b>" in message.last_reply
    assert "<b>4.</b>" not in message.last_reply


async def test_card_shows_details_and_actions(session, household, member, category):
    expense = await make(session, household, member, category, 250, description="кава")
    callback = FakeCallback()

    await show_expense(
        callback,
        callback_data=ExpenseCb(action="view", expense_id=expense.id),
        session=session,
        member=member,
    )

    text, kwargs = callback.message.replies[-1]
    assert f"Витрата #{expense.id}" in text
    assert "Автор: Сергій" in text
    labels = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any("Редагувати" in label for label in labels)
    assert any("Видалити" in label for label in labels)


async def test_card_for_missing_expense_reports_alert(session, member, category):
    callback = FakeCallback()

    await show_expense(
        callback,
        callback_data=ExpenseCb(action="view", expense_id=999),
        session=session,
        member=member,
    )

    assert callback.answers[-1][1] is True
    assert callback.message.replies == []
```

- [ ] **Step 3: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_expense_list.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot.handlers.expense_list'`

- [ ] **Step 4: Додати клавіатури**

Додати в `tg-bot/src/budget_bot/bot/keyboards.py`:

```python
from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.models import Expense


def expense_index_keyboard(expenses: Sequence[Expense]) -> InlineKeyboardMarkup:
    """One numbered button per listed row — the shortcut into the expense card."""
    builder = InlineKeyboardBuilder()
    for number, expense in enumerate(expenses, start=1):
        builder.button(
            text=str(number), callback_data=ExpenseCb(action="view", expense_id=expense.id)
        )
    builder.adjust(5)
    return builder.as_markup()


def expense_card_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редагувати", callback_data=ExpenseCb(action="edit", expense_id=expense_id))
    builder.button(text="🗑 Видалити", callback_data=ExpenseCb(action="delete", expense_id=expense_id))
    builder.adjust(2)
    return builder.as_markup()
```

- [ ] **Step 5: Реалізувати хендлери**

`tg-bot/src/budget_bot/bot/handlers/expense_list.py`:

```python
"""/list: recent expenses plus the per-record card."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.keyboards import BTN_LIST, expense_card_keyboard, expense_index_keyboard
from budget_bot.bot.texts import EMPTY_LIST_TEXT, MISSING_EXPENSE_TEXT
from budget_bot.config import Settings
from budget_bot.formatting import format_expense_card, format_expense_list
from budget_bot.models import Member
from budget_bot.services.expenses import ExpenseFilters, get_expense, list_expenses

router = Router(name="expense_list")


@router.message(Command("list"))
@router.message(F.text == BTN_LIST)
async def cmd_list(
    message: Message, session: AsyncSession, member: Member, settings: Settings
) -> None:
    expenses = await list_expenses(
        session, member.household_id, ExpenseFilters(limit=settings.recent_expenses_limit)
    )
    await message.answer(
        format_expense_list(expenses, "Останні витрати", EMPTY_LIST_TEXT),
        reply_markup=expense_index_keyboard(expenses) if expenses else None,
    )


@router.callback_query(ExpenseCb.filter(F.action == "view"))
async def show_expense(
    callback: CallbackQuery,
    callback_data: ExpenseCb,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await callback.message.answer(
        format_expense_card(expense), reply_markup=expense_card_keyboard(expense.id)
    )
    await callback.answer()
```

- [ ] **Step 6: Підключити роутер і запустити тести**

`build_router()`: `common.router, add_expense.router, categories.router, expense_list.router`.

Run: `cd tg-bot && .venv/bin/pytest -v`
Expected: усі passed

- [ ] **Step 7: Коміт**

```bash
git add tg-bot/src/budget_bot/bot tg-bot/tests
git commit -m "feat: add recent expenses list and expense card"
```

---

### Task 14: Expense filters (/filter)

**Files:**
- Create: `tg-bot/src/budget_bot/bot/handlers/filters.py`
- Modify: `tg-bot/src/budget_bot/bot/handlers/__init__.py`
- Modify: `tg-bot/src/budget_bot/bot/keyboards.py` (додати `filter_periods_keyboard`, `filter_categories_keyboard`, `filter_members_keyboard`)
- Test: `tg-bot/tests/test_handlers_filters.py`

**Interfaces:**
- Consumes: `budget_bot.periods.{Period, period_range, parse_custom_range}`, `budget_bot.clock.utcnow`, `budget_bot.services.access.list_members`, `budget_bot.services.categories.list_categories`, `budget_bot.services.expenses.{ExpenseFilters, list_expenses}`, `FilterCb`.
- Produces: `budget_bot.bot.handlers.filters` з `router`, `MAX_FILTER_RESULTS = 30`, `FilterFlow(StatesGroup)` зі станами `choosing, custom_range`, і хендлерами `cmd_filter(message, state)`, `choose_period(callback, callback_data, state, session, member)`, `enter_custom_range(message, state, session, member)`, `choose_category(callback, callback_data, state, session, member)`, `choose_member(callback, callback_data, state, session, member)`; `keyboards.filter_periods_keyboard()`, `keyboards.filter_categories_keyboard(categories)`, `keyboards.filter_members_keyboard(members)`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_handlers_filters.py`:

```python
from datetime import datetime

from budget_bot.bot.callbacks import FilterCb
from budget_bot.bot.handlers.filters import (
    FilterFlow,
    choose_category,
    choose_member,
    choose_period,
    cmd_filter,
    enter_custom_range,
)
from budget_bot.clock import utcnow
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense
from tests.conftest import FakeCallback, FakeMessage


async def make(session, household, member, category, amount, when=None):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        created_at=when or utcnow(),
    )


async def run_flow(session, member, state, *, period="month", category="all", author="all"):
    callback = FakeCallback()
    await choose_period(
        callback,
        callback_data=FilterCb(step="period", value=period),
        state=state,
        session=session,
        member=member,
    )
    await choose_category(
        callback,
        callback_data=FilterCb(step="category", value=category),
        state=state,
        session=session,
        member=member,
    )
    await choose_member(
        callback,
        callback_data=FilterCb(step="member", value=author),
        state=state,
        session=session,
        member=member,
    )
    return callback


async def test_filter_starts_with_period_choice(state):
    message = FakeMessage(text="/filter")

    await cmd_filter(message, state=state)

    assert await state.get_state() == FilterFlow.choosing
    assert "період" in message.last_reply.lower()


async def test_filter_by_current_month_returns_matching_records(
    session, household, member, category, state
):
    await make(session, household, member, category, 500)
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = await run_flow(session, member, state)

    assert "500" in callback.message.last_reply
    assert await state.get_state() is None


async def test_filter_by_category_excludes_others(
    session, household, member, category, state
):
    coffee = await add_category(session, household.id, "Кава")
    await make(session, household, member, category, 500)
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=coffee.id,
        amount=77,
        created_at=utcnow(),
    )
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = await run_flow(session, member, state, category=str(coffee.id))

    assert "77" in callback.message.last_reply
    assert "500" not in callback.message.last_reply


async def test_filter_by_author_excludes_partner(
    session, household, member, partner, category, state
):
    await make(session, household, member, category, 500)
    await make(session, household, partner, category, 77)
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = await run_flow(session, member, state, author=str(partner.id))

    assert "Оля" in callback.message.last_reply
    assert "500" not in callback.message.last_reply


async def test_empty_result_has_a_clear_message(session, member, category, state):
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = await run_flow(session, member, state)

    assert "Витрат за цей період не знайдено" in callback.message.last_reply


async def test_custom_range_is_validated_and_applied(
    session, household, member, category, state
):
    await make(session, household, member, category, 500, when=datetime(2026, 9, 7, 9, 0))
    await cmd_filter(FakeMessage(text="/filter"), state=state)

    callback = FakeCallback()
    await choose_period(
        callback,
        callback_data=FilterCb(step="period", value="custom"),
        state=state,
        session=session,
        member=member,
    )
    assert await state.get_state() == FilterFlow.custom_range

    bad = FakeMessage(text="вчора")
    await enter_custom_range(bad, state=state, session=session, member=member)
    assert await state.get_state() == FilterFlow.custom_range
    assert "Формат" in bad.last_reply

    good = FakeMessage(text="01.09.2026-30.09.2026")
    await enter_custom_range(good, state=state, session=session, member=member)
    assert await state.get_state() == FilterFlow.choosing

    await choose_category(
        FakeCallback(),
        callback_data=FilterCb(step="category", value="all"),
        state=state,
        session=session,
        member=member,
    )
    result = FakeCallback()
    await choose_member(
        result,
        callback_data=FilterCb(step="member", value="all"),
        state=state,
        session=session,
        member=member,
    )

    assert "500" in result.message.last_reply
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot.handlers.filters'`

- [ ] **Step 3: Додати клавіатури**

Додати в `tg-bot/src/budget_bot/bot/keyboards.py`:

```python
from budget_bot.bot.callbacks import FilterCb
from budget_bot.models import Member
from budget_bot.periods import PERIOD_TITLES, Period


def filter_periods_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in (Period.TODAY, Period.WEEK, Period.MONTH):
        builder.button(
            text=PERIOD_TITLES[period],
            callback_data=FilterCb(step="period", value=period.value),
        )
    builder.button(text="📅 Довільний період", callback_data=FilterCb(step="period", value="custom"))
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def filter_categories_keyboard(categories: Sequence[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Усі категорії", callback_data=FilterCb(step="category", value="all"))
    for item in categories:
        builder.button(
            text=item.name, callback_data=FilterCb(step="category", value=str(item.id))
        )
    builder.adjust(1, 2)
    return builder.as_markup()


def filter_members_keyboard(members: Sequence[Member]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Усі учасники", callback_data=FilterCb(step="member", value="all"))
    for item in members:
        builder.button(
            text=item.display_name, callback_data=FilterCb(step="member", value=str(item.id))
        )
    builder.adjust(1, 2)
    return builder.as_markup()
```

- [ ] **Step 4: Реалізувати хендлери**

`tg-bot/src/budget_bot/bot/handlers/filters.py`:

```python
"""/filter: period → category → author, then the matching list."""

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import FilterCb
from budget_bot.bot.keyboards import (
    BTN_FILTER,
    cancel_keyboard,
    expense_index_keyboard,
    filter_categories_keyboard,
    filter_members_keyboard,
    filter_periods_keyboard,
)
from budget_bot.clock import utcnow
from budget_bot.formatting import format_expense_list
from budget_bot.models import Member
from budget_bot.periods import Period, PeriodRange, parse_custom_range, period_range
from budget_bot.services.access import list_members
from budget_bot.services.categories import list_categories
from budget_bot.bot.texts import EMPTY_RESULT_TEXT
from budget_bot.services.expenses import ExpenseFilters, list_expenses

MAX_FILTER_RESULTS = 30

router = Router(name="filters")


class FilterFlow(StatesGroup):
    choosing = State()
    custom_range = State()


@router.message(Command("filter"))
@router.message(F.text == BTN_FILTER)
async def cmd_filter(message: Message, state: FSMContext) -> None:
    await state.set_state(FilterFlow.choosing)
    await state.set_data({})
    await message.answer("Оберіть період:", reply_markup=filter_periods_keyboard())


@router.callback_query(FilterFlow.choosing, FilterCb.filter(F.step == "period"))
async def choose_period(
    callback: CallbackQuery,
    callback_data: FilterCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    if callback_data.value == "custom":
        await state.set_state(FilterFlow.custom_range)
        await callback.message.answer(
            "Введіть діапазон у форматі ДД.ММ.РРРР-ДД.ММ.РРРР:",
            reply_markup=cancel_keyboard(),
        )
        await callback.answer()
        return

    await state.update_data(period=callback_data.value)
    await _ask_category(callback.message, session, member)
    await callback.answer()


@router.message(FilterFlow.custom_range)
async def enter_custom_range(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    raw = (message.text or "").strip()
    try:
        parse_custom_range(raw)
    except ValueError as error:
        await message.answer(f"⚠️ {error}", reply_markup=cancel_keyboard())
        return

    await state.update_data(period="custom", custom_range=raw)
    await state.set_state(FilterFlow.choosing)
    await _ask_category(message, session, member)


@router.callback_query(FilterFlow.choosing, FilterCb.filter(F.step == "category"))
async def choose_category(
    callback: CallbackQuery,
    callback_data: FilterCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    value = callback_data.value
    await state.update_data(category_id=None if value == "all" else int(value))
    members = await list_members(session, member.household_id)
    await callback.message.answer("Оберіть автора:", reply_markup=filter_members_keyboard(members))
    await callback.answer()


@router.callback_query(FilterFlow.choosing, FilterCb.filter(F.step == "member"))
async def choose_member(
    callback: CallbackQuery,
    callback_data: FilterCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    value = callback_data.value
    data = await state.update_data(member_id=None if value == "all" else int(value))
    await state.clear()

    period = _resolve_period(data)
    expenses = await list_expenses(
        session,
        member.household_id,
        ExpenseFilters(
            period=period,
            category_id=data.get("category_id"),
            member_id=data.get("member_id"),
            limit=MAX_FILTER_RESULTS,
        ),
    )
    header = "Знайдені витрати" if period is None else f"Витрати — {period.label}"
    await callback.message.answer(
        format_expense_list(expenses, header, EMPTY_RESULT_TEXT),
        reply_markup=expense_index_keyboard(expenses) if expenses else None,
    )
    await callback.answer()


async def _ask_category(message: Message, session: AsyncSession, member: Member) -> None:
    categories = await list_categories(session, member.household_id)
    await message.answer(
        "Оберіть категорію:", reply_markup=filter_categories_keyboard(categories)
    )


def _resolve_period(data: dict[str, Any]) -> PeriodRange | None:
    value = data.get("period")
    if value is None:
        return None
    if value == "custom":
        return parse_custom_range(data["custom_range"])
    return period_range(Period(value), utcnow())
```

- [ ] **Step 5: Підключити роутер і запустити тести**

`build_router()`: `common, add_expense, categories, expense_list, filters`.

Run: `cd tg-bot && .venv/bin/pytest -v`
Expected: усі passed

- [ ] **Step 6: Коміт**

```bash
git add tg-bot/src/budget_bot/bot tg-bot/tests/test_handlers_filters.py
git commit -m "feat: add expense filtering by period, category and author"
```

---

### Task 15: Editing an expense

**Files:**
- Create: `tg-bot/src/budget_bot/bot/handlers/expense_edit.py`
- Modify: `tg-bot/src/budget_bot/bot/handlers/__init__.py`
- Modify: `tg-bot/src/budget_bot/bot/keyboards.py` (додати `edit_fields_keyboard`)
- Test: `tg-bot/tests/test_handlers_expense_edit.py`

**Interfaces:**
- Consumes: `budget_bot.services.expenses.{get_expense, update_expense}`, `budget_bot.amounts.{parse_amount, AmountError}`, `budget_bot.services.categories.{list_categories, get_category}`, `budget_bot.formatting.format_expense_card`, `ExpenseCb`, `EditFieldCb`, `CategoryCb`.
- Produces: `budget_bot.bot.handlers.expense_edit` з `router`, `EditExpense(StatesGroup)` зі станами `amount, description, category`, і хендлерами `cb_edit_menu(callback, callback_data, session, member)`, `cb_pick_field(callback, callback_data, state, session, member)`, `enter_new_amount(message, state, session, member)`, `enter_new_description(message, state, session, member)`, `pick_new_category(callback, callback_data, state, session, member)`; `keyboards.edit_fields_keyboard(expense_id)`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_handlers_expense_edit.py`:

```python
from budget_bot.bot.callbacks import CategoryCb, EditFieldCb, ExpenseCb
from budget_bot.bot.handlers.expense_edit import (
    EditExpense,
    cb_edit_menu,
    cb_pick_field,
    enter_new_amount,
    enter_new_description,
    pick_new_category,
)
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense, get_expense
from tests.conftest import FakeCallback, FakeMessage


async def make(session, household, member, category, amount=250, description="кава"):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        description=description,
    )


async def test_edit_menu_offers_three_fields(session, household, member, category):
    expense = await make(session, household, member, category)
    callback = FakeCallback()

    await cb_edit_menu(
        callback,
        callback_data=ExpenseCb(action="edit", expense_id=expense.id),
        session=session,
        member=member,
    )

    labels = [
        button.text
        for row in callback.message.replies[-1][1]["reply_markup"].inline_keyboard
        for button in row
    ]
    assert any("Сума" in label for label in labels)
    assert any("Категорі" in label for label in labels)
    assert any("Опис" in label for label in labels)


async def test_partner_edits_amount_without_changing_the_author(
    session, household, member, partner, category, state
):
    expense = await make(session, household, member, category)

    await cb_pick_field(
        FakeCallback(),
        callback_data=EditFieldCb(field="amount", expense_id=expense.id),
        state=state,
        session=session,
        member=partner,
    )
    assert await state.get_state() == EditExpense.amount

    message = FakeMessage(text="300")
    await enter_new_amount(message, state=state, session=session, member=partner)

    updated = await get_expense(session, household.id, expense.id)
    assert updated.amount == 300
    assert updated.member_id == member.id
    assert updated.updated_by_id == partner.id
    assert "Змінив(ла): Оля" in message.last_reply
    assert await state.get_state() is None


async def test_invalid_new_amount_keeps_state(session, household, member, category, state):
    expense = await make(session, household, member, category)
    await state.set_state(EditExpense.amount)
    await state.update_data(expense_id=expense.id)

    message = FakeMessage(text="-5")
    await enter_new_amount(message, state=state, session=session, member=member)

    assert await state.get_state() == EditExpense.amount
    assert (await get_expense(session, household.id, expense.id)).amount == 250


async def test_edit_description_and_clearing_it(
    session, household, member, category, state
):
    expense = await make(session, household, member, category)
    await state.set_state(EditExpense.description)
    await state.update_data(expense_id=expense.id)

    await enter_new_description(FakeMessage(text="обід"), state=state, session=session, member=member)
    assert (await get_expense(session, household.id, expense.id)).description == "обід"

    await state.set_state(EditExpense.description)
    await state.update_data(expense_id=expense.id)
    await enter_new_description(FakeMessage(text="-"), state=state, session=session, member=member)
    assert (await get_expense(session, household.id, expense.id)).description is None


async def test_edit_category(session, household, member, category, state):
    expense = await make(session, household, member, category)
    coffee = await add_category(session, household.id, "Кава")
    await state.set_state(EditExpense.category)
    await state.update_data(expense_id=expense.id)

    await pick_new_category(
        FakeCallback(),
        callback_data=CategoryCb(action="edit", category_id=coffee.id),
        state=state,
        session=session,
        member=member,
    )

    updated = await get_expense(session, household.id, expense.id)
    assert updated.category_id == coffee.id
    assert await state.get_state() is None


async def test_editing_a_deleted_expense_reports_alert(session, member, category, state):
    callback = FakeCallback()

    await cb_edit_menu(
        callback,
        callback_data=ExpenseCb(action="edit", expense_id=999),
        session=session,
        member=member,
    )

    assert callback.answers[-1][1] is True
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_expense_edit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot.handlers.expense_edit'`

- [ ] **Step 3: Додати клавіатуру**

Додати в `tg-bot/src/budget_bot/bot/keyboards.py`:

```python
from budget_bot.bot.callbacks import EditFieldCb


def edit_fields_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Сума", callback_data=EditFieldCb(field="amount", expense_id=expense_id))
    builder.button(
        text="🏷 Категорія", callback_data=EditFieldCb(field="category", expense_id=expense_id)
    )
    builder.button(
        text="📝 Опис", callback_data=EditFieldCb(field="description", expense_id=expense_id)
    )
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(3, 1)
    return builder.as_markup()
```

- [ ] **Step 4: Реалізувати хендлери**

`tg-bot/src/budget_bot/bot/handlers/expense_edit.py`:

```python
"""Editing an existing expense. Any member may edit any record."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.amounts import AmountError, parse_amount
from budget_bot.bot.callbacks import CategoryCb, EditFieldCb, ExpenseCb
from budget_bot.bot.keyboards import (
    cancel_keyboard,
    categories_keyboard,
    edit_fields_keyboard,
)
from budget_bot.bot.texts import (
    CLEAR_DESCRIPTION_TOKEN,
    MAX_DESCRIPTION_LENGTH,
    MISSING_EXPENSE_TEXT,
)
from budget_bot.formatting import format_expense_card
from budget_bot.models import Member
from budget_bot.services.categories import get_category, list_categories
from budget_bot.services.expenses import get_expense, update_expense

router = Router(name="expense_edit")


class EditExpense(StatesGroup):
    amount = State()
    description = State()
    category = State()


@router.callback_query(ExpenseCb.filter(F.action == "edit"))
async def cb_edit_menu(
    callback: CallbackQuery,
    callback_data: ExpenseCb,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await callback.message.answer(
        "Що змінюємо?", reply_markup=edit_fields_keyboard(expense.id)
    )
    await callback.answer()


@router.callback_query(EditFieldCb.filter())
async def cb_pick_field(
    callback: CallbackQuery,
    callback_data: EditFieldCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await state.update_data(expense_id=expense.id)

    if callback_data.field == "amount":
        await state.set_state(EditExpense.amount)
        await callback.message.answer("Введіть нову суму:", reply_markup=cancel_keyboard())
    elif callback_data.field == "description":
        await state.set_state(EditExpense.description)
        await callback.message.answer(
            f"Введіть новий опис (або «{CLEAR_DESCRIPTION_TOKEN}», щоб прибрати):",
            reply_markup=cancel_keyboard(),
        )
    else:
        await state.set_state(EditExpense.category)
        categories = await list_categories(session, member.household_id)
        await callback.message.answer(
            "Оберіть нову категорію:",
            reply_markup=categories_keyboard(categories, action="edit"),
        )
    await callback.answer()


@router.message(EditExpense.amount)
async def enter_new_amount(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        amount = parse_amount(message.text or "")
    except AmountError as error:
        await message.answer(f"⚠️ {error}", reply_markup=cancel_keyboard())
        return

    await _apply(message, state, session, member, amount=amount)


@router.message(EditExpense.description)
async def enter_new_description(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    raw = (message.text or "").strip()
    description = None if raw == CLEAR_DESCRIPTION_TOKEN else raw[:MAX_DESCRIPTION_LENGTH] or None
    await _apply(message, state, session, member, description=description)


@router.callback_query(EditExpense.category, CategoryCb.filter(F.action == "edit"))
async def pick_new_category(
    callback: CallbackQuery,
    callback_data: CategoryCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    category = await get_category(session, member.household_id, callback_data.category_id)
    if category is None:
        await callback.answer("Категорію не знайдено. Оберіть іншу.", show_alert=True)
        return

    await _apply(callback.message, state, session, member, category_id=category.id)
    await callback.answer()


async def _apply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
    **changes,
) -> None:
    data = await state.get_data()
    expense = await get_expense(session, member.household_id, data["expense_id"])
    if expense is None:
        await state.clear()
        await message.answer(MISSING_EXPENSE_TEXT)
        return

    await update_expense(session, expense, editor_id=member.id, **changes)
    await state.clear()
    await message.answer(f"✅ Оновлено.\n\n{format_expense_card(expense)}")
```

- [ ] **Step 5: Підключити роутер і запустити тести**

`build_router()`: `common, add_expense, categories, expense_list, filters, expense_edit`.

Run: `cd tg-bot && .venv/bin/pytest -v`
Expected: усі passed

- [ ] **Step 6: Коміт**

```bash
git add tg-bot/src/budget_bot/bot tg-bot/tests/test_handlers_expense_edit.py
git commit -m "feat: add expense editing with editor tracking"
```

---
### Task 16: Deleting an expense

**Files:**
- Create: `tg-bot/src/budget_bot/bot/handlers/expense_delete.py`
- Modify: `tg-bot/src/budget_bot/bot/handlers/__init__.py`
- Modify: `tg-bot/src/budget_bot/bot/keyboards.py` (додати `delete_confirm_keyboard`)
- Test: `tg-bot/tests/test_handlers_expense_delete.py`

**Interfaces:**
- Consumes: `budget_bot.services.expenses.{get_expense, delete_expense, list_expenses}`, `budget_bot.formatting.format_expense_card`, `ExpenseCb`.
- Produces: `budget_bot.bot.handlers.expense_delete` з `router`, `cb_ask_delete(callback, callback_data, session, member)`, `cb_do_delete(callback, callback_data, session, member)`; `keyboards.delete_confirm_keyboard(expense_id)`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_handlers_expense_delete.py`:

```python
from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.handlers.expense_delete import cb_ask_delete, cb_do_delete
from budget_bot.clock import utcnow
from budget_bot.periods import Period, period_range
from budget_bot.services.expenses import create_expense, get_expense, list_expenses
from budget_bot.services.reports import build_report
from tests.conftest import FakeCallback


async def make(session, household, member, category, amount=250):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
    )


async def test_delete_asks_for_confirmation_first(session, household, member, category):
    expense = await make(session, household, member, category)
    callback = FakeCallback()

    await cb_ask_delete(
        callback,
        callback_data=ExpenseCb(action="delete", expense_id=expense.id),
        session=session,
        member=member,
    )

    text, kwargs = callback.message.replies[-1]
    assert "Видалити" in text
    labels = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any("Так" in label for label in labels)
    assert any("Ні" in label for label in labels)
    assert await get_expense(session, household.id, expense.id) is not None


async def test_confirmed_delete_removes_from_lists_and_reports(
    session, household, member, category
):
    expense = await make(session, household, member, category, amount=250)
    callback = FakeCallback()

    await cb_do_delete(
        callback,
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense.id),
        session=session,
        member=member,
    )

    assert await get_expense(session, household.id, expense.id) is None
    assert await list_expenses(session, household.id) == []
    report = await build_report(session, household.id, period_range(Period.YEAR, utcnow()))
    assert report.total == 0
    assert "видалено" in callback.message.last_edit


async def test_partner_can_delete_someone_elses_expense(
    session, household, member, partner, category
):
    expense = await make(session, household, member, category)

    await cb_do_delete(
        FakeCallback(),
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense.id),
        session=session,
        member=partner,
    )

    assert await get_expense(session, household.id, expense.id) is None


async def test_deleting_twice_reports_alert(session, household, member, category):
    expense = await make(session, household, member, category)
    await cb_do_delete(
        FakeCallback(),
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense.id),
        session=session,
        member=member,
    )

    second = FakeCallback()
    await cb_do_delete(
        second,
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense.id),
        session=session,
        member=member,
    )

    assert second.answers[-1][1] is True
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_expense_delete.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot.handlers.expense_delete'`

- [ ] **Step 3: Додати клавіатуру**

Додати в `tg-bot/src/budget_bot/bot/keyboards.py`:

```python
def delete_confirm_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗑 Так, видалити",
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense_id),
    )
    builder.button(
        text="↩️ Ні", callback_data=ExpenseCb(action="view", expense_id=expense_id)
    )
    builder.adjust(2)
    return builder.as_markup()
```

- [ ] **Step 4: Реалізувати хендлери**

`tg-bot/src/budget_bot/bot/handlers/expense_delete.py`:

```python
"""Deleting an expense, always behind an explicit confirmation."""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import ExpenseCb
from budget_bot.bot.keyboards import delete_confirm_keyboard
from budget_bot.bot.texts import MISSING_EXPENSE_TEXT
from budget_bot.formatting import format_expense_card
from budget_bot.models import Member
from budget_bot.services.expenses import delete_expense, get_expense

router = Router(name="expense_delete")


@router.callback_query(ExpenseCb.filter(F.action == "delete"))
async def cb_ask_delete(
    callback: CallbackQuery,
    callback_data: ExpenseCb,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await callback.message.answer(
        f"Видалити цей запис?\n\n{format_expense_card(expense)}",
        reply_markup=delete_confirm_keyboard(expense.id),
    )
    await callback.answer()


@router.callback_query(ExpenseCb.filter(F.action == "delete_yes"))
async def cb_do_delete(
    callback: CallbackQuery,
    callback_data: ExpenseCb,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    await delete_expense(session, expense)
    await callback.message.edit_text("🗑 Запис видалено.")
    await callback.answer()
```

- [ ] **Step 5: Підключити роутер і запустити тести**

`build_router()`: `common, add_expense, categories, expense_list, filters, expense_edit, expense_delete`.

Run: `cd tg-bot && .venv/bin/pytest -v`
Expected: усі passed

- [ ] **Step 6: Коміт**

```bash
git add tg-bot/src/budget_bot/bot tg-bot/tests/test_handlers_expense_delete.py
git commit -m "feat: add expense deletion with confirmation"
```

---

### Task 17: Reports handler (/report)

**Files:**
- Create: `tg-bot/src/budget_bot/bot/handlers/reports.py`
- Modify: `tg-bot/src/budget_bot/bot/handlers/__init__.py`
- Modify: `tg-bot/src/budget_bot/bot/keyboards.py` (додати `report_periods_keyboard`)
- Test: `tg-bot/tests/test_handlers_reports.py`

**Interfaces:**
- Consumes: `budget_bot.periods.{Period, PERIOD_TITLES, period_range}`, `budget_bot.clock.utcnow`, `budget_bot.services.reports.build_report`, `budget_bot.formatting.format_report`, `ReportCb`.
- Produces: `budget_bot.bot.handlers.reports` з `router`, `REPORT_PERIODS: tuple[Period, ...]`, `cmd_report(message)`, `cb_report(callback, callback_data, session, member)`; `keyboards.report_periods_keyboard()`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_handlers_reports.py`:

```python
from budget_bot.bot.callbacks import ReportCb
from budget_bot.bot.handlers.reports import cb_report, cmd_report
from budget_bot.clock import utcnow
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense
from tests.conftest import FakeCallback, FakeMessage


async def make(session, household, member, category, amount):
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        created_at=utcnow(),
    )


async def test_report_command_offers_week_month_year():
    message = FakeMessage(text="/report")

    await cmd_report(message)

    labels = [
        b.text for row in message.replies[-1][1]["reply_markup"].inline_keyboard for b in row
    ]
    assert any("тиждень" in label.lower() for label in labels)
    assert any("місяць" in label.lower() for label in labels)
    assert any("рік" in label.lower() for label in labels)
    assert not any("сьогодні" in label.lower() for label in labels)


async def test_month_report_shows_totals_by_category_and_member(
    session, household, member, partner, category
):
    coffee = await add_category(session, household.id, "Кава")
    await make(session, household, member, category, 600)
    await make(session, household, partner, category, 200)
    await make(session, household, partner, coffee, 200)
    callback = FakeCallback()

    await cb_report(
        callback, callback_data=ReportCb(period="month"), session=session, member=member
    )

    text = callback.message.last_edit
    assert "Разом" in text
    assert "Їжа" in text and "80.0%" in text
    assert "Сергій" in text and "Оля" in text


async def test_empty_report_says_so_without_error(session, member, category):
    callback = FakeCallback()

    await cb_report(
        callback, callback_data=ReportCb(period="year"), session=session, member=member
    )

    assert "Витрат за цей період не знайдено" in callback.message.last_edit
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd tg-bot && .venv/bin/pytest tests/test_handlers_reports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot.handlers.reports'`

- [ ] **Step 3: Додати клавіатуру**

Додати в `tg-bot/src/budget_bot/bot/keyboards.py`:

```python
from budget_bot.bot.callbacks import ReportCb


def report_periods_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in (Period.WEEK, Period.MONTH, Period.YEAR):
        builder.button(
            text=PERIOD_TITLES[period], callback_data=ReportCb(period=period.value)
        )
    builder.adjust(1)
    return builder.as_markup()
```

- [ ] **Step 4: Реалізувати хендлери**

`tg-bot/src/budget_bot/bot/handlers/reports.py`:

```python
"""/report: текстовий звіт за календарний тиждень / місяць / рік."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import ReportCb
from budget_bot.bot.keyboards import BTN_REPORT, report_periods_keyboard
from budget_bot.clock import utcnow
from budget_bot.formatting import format_report
from budget_bot.models import Member
from budget_bot.periods import Period, period_range
from budget_bot.services.reports import build_report

REPORT_PERIODS = (Period.WEEK, Period.MONTH, Period.YEAR)

router = Router(name="reports")


@router.message(Command("report"))
@router.message(F.text == BTN_REPORT)
async def cmd_report(message: Message) -> None:
    await message.answer("Оберіть період звіту:", reply_markup=report_periods_keyboard())


@router.callback_query(ReportCb.filter())
async def cb_report(
    callback: CallbackQuery,
    callback_data: ReportCb,
    session: AsyncSession,
    member: Member,
) -> None:
    period = period_range(Period(callback_data.period), utcnow())
    report = await build_report(session, member.household_id, period)
    await callback.message.edit_text(format_report(report))
    await callback.answer()
```

- [ ] **Step 5: Підключити роутер і прогнати весь набір**

`build_router()` — фінальний склад:

```python
from budget_bot.bot.handlers import (
    add_expense,
    categories,
    common,
    expense_delete,
    expense_edit,
    expense_list,
    filters,
    reports,
)


def build_router() -> Router:
    router = Router(name="root")
    # common goes first: /cancel must beat any FSM-state handler.
    router.include_routers(
        common.router,
        add_expense.router,
        categories.router,
        expense_list.router,
        filters.router,
        expense_edit.router,
        expense_delete.router,
        reports.router,
    )
    return router
```

Run: `cd tg-bot && .venv/bin/pytest -v && .venv/bin/ruff check . && .venv/bin/black --check .`
Expected: усе зелене

- [ ] **Step 6: Коміт**

```bash
git add tg-bot/src/budget_bot/bot tg-bot/tests/test_handlers_reports.py
git commit -m "feat: add text reports for week, month and year"
```

---

### Task 18: Portable deployment and documentation

**Files:**
- Create: `tg-bot/Dockerfile`
- Create: `tg-bot/.dockerignore`
- Create: `tg-bot/docker-entrypoint.sh`
- Create: `tg-bot/docker-compose.yml`
- Create: `tg-bot/README.md`
- Modify: `CLAUDE.md` (секція «Статус»)

**Interfaces:**
- Consumes: `python -m budget_bot` як точку входу, `DATABASE_PATH` як env.
- Produces: образ, який запускає `alembic upgrade head` і далі бота; `docker compose up` для локального прогону.

- [ ] **Step 1: Написати `docker-entrypoint.sh`**

```sh
#!/bin/sh
set -e

DB_PATH="${DATABASE_PATH:-/data/budget.sqlite3}"
mkdir -p "$(dirname "$DB_PATH")"

echo "Applying database migrations..."
alembic upgrade head

exec "$@"
```

- [ ] **Step 2: Написати `Dockerfile` і `.dockerignore`**

`tg-bot/Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_PATH=/data/budget.sqlite3

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# SQLite must live on a persistent volume — a redeploy wipes the container FS.
VOLUME ["/data"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "budget_bot"]
```

`tg-bot/.dockerignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
*.egg-info/
tests/
data/
.env
.git/
```

- [ ] **Step 3: Написати `docker-compose.yml`**

```yaml
services:
  bot:
    build: .
    env_file: .env
    environment:
      DATABASE_PATH: /data/budget.sqlite3
    volumes:
      - budget-data:/data
    restart: unless-stopped

volumes:
  budget-data:
```

- [ ] **Step 4: Написати `README.md`**

`tg-bot/README.md`:

````markdown
# Telegram-бот сімейного бюджету

Скоуп і вимоги — у `../docs/requirements.md`. План імплементації — у
`../docs/superpowers/plans/2026-09-07-telegram-budget-bot-mvp.md`.

## Локальний запуск

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # заповнити TELEGRAM_BOT_TOKEN і ALLOWED_TELEGRAM_IDS
.venv/bin/alembic upgrade head
.venv/bin/python -m budget_bot
```

Свій Telegram ID можна дізнатись у @userinfobot.

## Тести і лінт

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/black --check .
```

## Docker

```bash
docker compose up --build
```

Міграції застосовуються автоматично при старті контейнера.

## Деплой

Провайдер (Railway / Fly.io) ще не обрано, тому образ навмисно портативний.
Вимоги до будь-якої платформи:

1. **Persistent volume, змонтований у `/data`** — там лежить `budget.sqlite3`.
   Без тому дані зникнуть при першому ж редеплої.
2. **Змінні середовища:** `TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_IDS`,
   опційно `HOUSEHOLD_NAME`, `DATABASE_PATH`, `RECENT_EXPENSES_LIMIT`.
3. **Рівно один інстанс.** Бот працює через long polling; два інстанси на
   одному токені почнуть конфліктувати за `getUpdates`.
4. **HTTP-порт не потрібен** — це worker-процес, не веб-сервіс. Якщо платформа
   вимагає health check, налаштуйте його на процес, а не на порт.

## Конфіг

| Змінна | Обовʼязкова | Значення за замовчуванням | Опис |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | так | — | Токен від @BotFather |
| `ALLOWED_TELEGRAM_IDS` | так | — | Telegram ID через кому |
| `HOUSEHOLD_NAME` | ні | `Сім'я` | Назва домогосподарства |
| `DATABASE_PATH` | ні | `data/budget.sqlite3` | Шлях до файлу SQLite |
| `RECENT_EXPENSES_LIMIT` | ні | `10` | Скільки записів показує `/list` |
````

- [ ] **Step 5: Перевірити, що образ збирається і мігрує**

```bash
cd tg-bot && docker build -t budget-bot:test .
docker run --rm -e TELEGRAM_BOT_TOKEN=x -e ALLOWED_TELEGRAM_IDS=1 \
  -v budget-test:/data budget-bot:test alembic current
```
Expected: збірка успішна, `alembic current` показує ревізію `0001` без помилок.

- [ ] **Step 6: Оновити статус у `CLAUDE.md`**

Замінити секцію «Статус» на:

```markdown
## Статус

MVP бота реалізовано в `tg-bot/` (aiogram 3 + SQLAlchemy 2 async + SQLite/Alembic,
запуск через Docker). `dashboard/` — усе ще порожньо. Деплой-провайдер ще не обрано:
образ портативний, потрібен лише persistent volume на `/data` і env-змінні
(див. `tg-bot/README.md`).
```

- [ ] **Step 7: Фінальна перевірка**

Run: `cd tg-bot && .venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/black --check .`
Expected: усе зелене

- [ ] **Step 8: Коміт**

```bash
git add tg-bot/Dockerfile tg-bot/.dockerignore tg-bot/docker-entrypoint.sh \
        tg-bot/docker-compose.yml tg-bot/README.md CLAUDE.md
git commit -m "docs: add portable Docker deployment and project README"
```

---

## Ручна приймальна перевірка (після Task 18)

Прогнати живим ботом з реальним токеном — це те, чого юніт-тести не покривають
(мережа Telegram, inline-клавіатури, реальний FSM):

1. Написати боту з **недозволеного** акаунта → «⛔️ Доступ заборонено», у БД нічого не зʼявилось.
2. `/start` з дозволеного акаунта → привітання з іменем + меню знизу.
3. `/categories` → 9 базових категорій. Додати «Кава». Спробувати додати «кава» → відмова з поясненням.
4. `/add` → `12.5` (відмова) → `250` → категорія «Їжа» → «Пропустити» → «Зберегти» → підсумок.
5. `/add` → `/cancel` посередині → нічого не збереглось (`/list` не змінився).
6. З другого акаунта: `/list` → бачить запис першого. Відредагувати суму → у картці зʼявилось «Змінив(ла)», автор лишився початковий.
7. `/filter` → «Довільний період» → крива дата (відмова) → коректний діапазон → категорія → автор → результат.
8. Видалити запис → підтвердження → `/report` за місяць більше його не враховує.
9. `/report` за рік з порожньою БД → «Витрат за цей період не знайдено», без помилки.
10. Перезапустити контейнер → `/list` показує ті самі записи (том працює).
