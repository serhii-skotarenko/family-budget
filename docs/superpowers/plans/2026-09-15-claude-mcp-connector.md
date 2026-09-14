# Claude MCP Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дати Claude (claude.ai, Desktop, мобільний застосунок, Claude Code) доступ на читання до витрат із бота через remote MCP-сервер, що працює в процесі бота.

**Architecture:** Новий пакет `budget_bot.connector` повторює шари бота: чистий розбір аргументів (`inputs`) → аналітика над `AsyncSession`, що повертає Pydantic-моделі (`analytics`, `schemas`) → MCP-інструменти (`tools`) → HTTP: Bearer-гейт (`auth`), конфіг, ASGI-застосунок і uvicorn (`server`). `__main__.run_bot` запускає uvicorn поруч з aiogram polling в одному asyncio-процесі; база відкривається окремим read-only engine.

**Tech Stack:** Python 3.12, MCP Python SDK `mcp==2.2.0` (`MCPServer`, streamable HTTP, stateless JSON), uvicorn 0.53, Starlette 1.6, SQLAlchemy 2.0 async + aiosqlite, pydantic 2, pytest + pytest-asyncio, ruff + black.

**Spec:** `docs/superpowers/specs/2026-09-15-claude-mcp-connector-design.md`

## Global Constraints

Ці правила діють у **кожній** задачі — не повторюються в описах окремих кроків.

- **Джерело правди — специфікація** (шлях вище). Якщо план і специфікація розійдуться — зупинитися й спитати.
- **Гілка:** `feat/claude-mcp-connector`. Усі команди виконуються з каталогу `tg-bot/`: `.venv/bin/python -m pytest …`, `.venv/bin/ruff check src tests`, `.venv/bin/black --check src tests`.
- **Тільки читання.** Конектор нічого не пише в БД; схема й міграції Alembic не змінюються.
- **Залежності:** `mcp==2.2.0` (точно), `uvicorn>=0.53,<0.54`. Нових dev-залежностей немає.
- **Ендпоінт** — `/mcp`, `stateless_http=True`, `json_response=True`.
- **Дати** — рядки `YYYY-MM-DD`, обидві межі включно, календарні дні `Europe/Kyiv`; роки 2000–2100. Дата витрати — `Expense.created_at` (момент запису в боті; у БД — UTC-naive).
- **Суми** — цілі гривні (`int`), валюта `UAH`.
- **Household** — `SINGLETON_HOUSEHOLD_ID` із `budget_bot.services.access`.
- **Інструменти:** назви англійською, `title` українською, описи англійською й фактичні — що повертає і в яких одиницях, без інструкцій моделі щодо поведінки. Кожен має `ToolAnnotations(read_only_hint=True, open_world_hint=False)`.
- **Логи ніколи не містять** значень токенів, сум, описів, назв категорій, імен учасників і аргументів викликів.
- **Збій конектора не зупиняє бота:** некоректний конфіг → ERROR у лозі, конектор вимкнено, бот стартує; падіння uvicorn, зокрема `SystemExit`, перехоплюється.
- **Автентифікація:** `MCP_ACCESS_TOKENS` = `label:token,label:token`, мітка `[a-z0-9_-]{1,32}`, токен ≥ 32 символи. Відмова — `401` з `WWW-Authenticate: Bearer`, без `resource_metadata`.
- **Host і Origin:** `allowed_hosts=[MCP_PUBLIC_HOST]`, `allowed_origins=["https://claude.ai"]`.
- **Мова:** код, докстрінги й commit-меседжі — англійською; prose у `README.md` і `CLAUDE.md` — українською. Коміти — conventional commits.
- **Тести:** справжній SQLite-файл, очікувані значення порахувані вручну (не кодом, що тестується), без моків БД.
- **Не запускати бота локально з бойовим токеном** із `tg-bot/.env`: прод на Railway уже опитує Telegram, другий процес отримає `TelegramConflictError`. Поведінку процесу перевіряє subprocess-тест із фейковою сесією Telegram (Task 9).
- **Секрети:** жодних токенів у репозиторії, тестах чи логах; `.env` не комітити.

## File Structure

Шляхи — відносно `tg-bot/`, крім `CLAUDE.md` у корені репозиторію.

| Файл | Дія | Відповідальність | Задача |
|---|---|---|---|
| `src/budget_bot/periods.py` | змінити | + `kyiv_day_range`; обидва будівники періодів переходять на нього | 1 |
| `src/budget_bot/db.py` | змінити | + `create_readonly_engine` | 1 |
| `src/budget_bot/connector/__init__.py` | створити | пакет конектора | 2 |
| `src/budget_bot/connector/inputs.py` | створити | розбір і валідація аргументів, `InvalidRequest` | 2 |
| `src/budget_bot/connector/schemas.py` | створити, розширити | Pydantic-моделі відповідей (контракт API) | 3, 4, 5 |
| `src/budget_bot/connector/analytics.py` | створити, розширити | пошук за назвою, огляд, підсумок, тренд, список | 3, 4, 5 |
| `src/budget_bot/connector/tools.py` | створити | `build_mcp_server`: 4 інструменти, мапінг помилок, лог викликів | 6 |
| `src/budget_bot/connector/auth.py` | створити | `parse_access_tokens`, ASGI-гейт `BearerGate` | 7 |
| `src/budget_bot/config.py` | змінити | + `MCP_ACCESS_TOKENS`, `MCP_PUBLIC_HOST`, `PORT` | 8 |
| `src/budget_bot/connector/server.py` | створити | `connector_config`, `build_connector_app`, `ConnectorServer`, `serve_connector` | 8 |
| `src/budget_bot/__main__.py` | змінити | `run_bot`; конектор у `main` | 9 |
| `pyproject.toml` | змінити | `mcp` (Task 6), `uvicorn` (Task 8) | 6, 8 |
| `tests/conftest.py` | змінити | фікстури справжньої файлової БД | 3 |
| `tests/test_periods.py`, `tests/test_db.py` | змінити | діапазони днів, read-only engine | 1 |
| `tests/test_connector_inputs.py` | створити | розбір аргументів | 2 |
| `tests/test_connector_summary.py` | створити | пошук за назвою, огляд, підсумок | 3 |
| `tests/test_connector_trend.py` | створити | кошики тренду, DST | 4 |
| `tests/test_connector_list.py` | створити | сортування, фільтри, сторінки | 5 |
| `tests/test_connector_tools.py` | створити | контракт MCP через `Client(server)` | 6 |
| `tests/test_connector_auth.py` | створити | розбір токенів, гейт | 7 |
| `tests/test_config.py` | змінити | нові змінні | 8 |
| `tests/test_connector_server.py` | створити | конфіг, HTTP-застосунок, зайнятий порт | 8 |
| `tests/connector_lifecycle_app.py` | створити | допоміжний застосунок для subprocess-тесту | 9 |
| `tests/test_connector_lifecycle.py` | створити | SIGTERM, порядок зупинки | 9 |
| `README.md`, `.env.example`, `docker-compose.yml`, `CLAUDE.md` | змінити | документація, локальний запуск | 10 |

## Перевірено до написання плану

Весь код цього плану прогнано начорно в копії репозиторію 2026-09-15: 258 тестів зелені, ruff і black чисті; проміжні версії `analytics.py` і `schemas.py` після Task 3 і Task 4 окремо пройшли свої тести й лінт. Факти, на які спирається код:

- **mcp 2.2.0:** `from mcp.server.mcpserver import Context, MCPServer`; `ToolError` — у `mcp.server.mcpserver.exceptions`; `from mcp_types import ToolAnnotations` (поля snake_case). Pydantic-модель, яку повертає інструмент, стає `structured_content` плюс текстовим JSON. Текст `ToolError` доходить до моделі з префіксом `Error executing tool <name>: `. Невалідний `Literal` чи відсутній аргумент SDK сам повертає як `is_error`. Описи з `Annotated[..., Field(description=...)]` потрапляють у вхідну схему.
- **SDK пише текст кожного `ToolError` у лог на INFO** (логер `mcp.server.mcpserver.server`). Наші повідомлення містять назви категорій і учасників, тож `build_mcp_server` піднімає рівень цього логера до WARNING. Без цього тест «логи без даних» у Task 6 падає.
- **Тести інструментів:** `async with Client(server) as client` працює в процесі; тоді `ctx.request_context.request` — `None`. Через HTTP це Starlette `Request`, і мітка, яку гейт кладе в `scope["state"]`, доходить до інструмента як `request.state.mcp_token_label`.
- **HTTP-застосунок SDK запускається лише раз** (`StreamableHTTPSessionManager .run() can only be called once per instance`) — у тестах новий застосунок на кожен `TestClient`.
- **Протокол:** `initialize`, `tools/list`, `tools/call` у stateless JSON-режимі працюють із версіями `2025-06-18` і `2025-11-25`; тести використовують `2025-11-25`. Чужий `Host` → 421, чужий `Origin` → 403, `/mcp/` → 307 на `/mcp`.
- **Starlette 1.6 `TestClient`** працює з `httpx2`, який тягне mcp, — окремий httpx не потрібен.
- **uvicorn 0.53** при зайнятому порті викликає `sys.exit(3)`. Якщо `serve_connector` не ловить `SystemExit`, тест зайнятого порту падає (перевірено мутацією).
- **Сигнали:** зі справжнім aiogram один SIGTERM зупиняє все чисто і без override `capture_signals`, але **повторний SIGTERM під час прибирання без override вбиває процес** (код −15). Тест `test_repeated_sigterm_during_cleanup_does_not_kill_the_process` падає, якщо override прибрати (перевірено мутацією).
- **Read-only SQLite у WAL:** `mode=ro` читає і коли бот тримає з'єднання, і коли ні; запис падає з `attempt to write a readonly database`.

## Покриття специфікації

| Розділ специфікації | Задачі |
|---|---|
| Архітектура, компоненти, потік запиту | 2–9 |
| Безпека → автентифікація | 7, 8 |
| Безпека → Host і Origin | 8 |
| Безпека → база лише для читання | 1 |
| Безпека → логи | 6, 7, 8 |
| Безпека → секрети | 10, «Після злиття» |
| Інструменти (API) | 3, 4, 5, 6 |
| Помилки | 2–6, 7, 8 |
| Конфігурація | 8, 9 |
| Життєвий цикл процесу | 8, 9 |
| Залежності | 6, 8 |
| Тестування | тести в кожній задачі; ручна перевірка — «Після злиття» |
| Деплой і підключення, перевірити під час деплою | 10, «Після злиття» |

Уточнення відносно тексту специфікації, знайдені під час перевірки:

- Аналітику (Tasks 3–5) тестуємо напряму на read-only сесії; через `Client(server)` (Task 6) — контракт MCP: метадані, структуровані результати, помилки, лог.
- `period_range` теж переходить на `kyiv_day_range` — там той самий дубльований код, що й у `parse_custom_range`.
- Рівень логера SDK піднято до WARNING (див. вище; специфікацію доповнено).

---

### Task 1: Kyiv day ranges and the read-only engine

**Files:**
- Modify: `tg-bot/src/budget_bot/periods.py`
- Modify: `tg-bot/src/budget_bot/db.py`
- Test: `tg-bot/tests/test_periods.py`, `tg-bot/tests/test_db.py`

**Interfaces:**
- Consumes: `budget_bot.periods.PeriodRange`, `budget_bot.periods._kyiv_midnight_as_utc` (наявні).
- Produces:
  - `budget_bot.periods.kyiv_day_range(first: date, last: date, label: str = "") -> PeriodRange` — напіввідкритий UTC-naive діапазон `[start, end)`, що покриває київські дні `first..last` включно.
  - `budget_bot.db.create_readonly_engine(database_path: Path) -> AsyncEngine` — SQLite `mode=ro` + `PRAGMA query_only=ON` + `PRAGMA busy_timeout=10000`.

- [ ] **Step 1: Написати падаючий тест `kyiv_day_range`**

У `tg-bot/tests/test_periods.py` замінити блок імпортів на:

```python
from datetime import date, datetime

import pytest

from budget_bot.periods import (
    Period,
    format_date_short,
    format_datetime,
    kyiv_day_range,
    parse_custom_range,
    period_range,
    to_kyiv,
)
```

і додати в кінець файлу:

```python


def test_kyiv_day_range_covers_whole_kyiv_days_across_the_dst_switch():
    # 25 October 2026 lasts 25 hours in Kyiv: summer time ends at 04:00.
    result = kyiv_day_range(date(2026, 10, 25), date(2026, 10, 25))
    assert result.start == datetime(2026, 10, 24, 21, 0)
    assert result.end == datetime(2026, 10, 25, 22, 0)
```

- [ ] **Step 2: Написати падаючі тести read-only engine**

`tg-bot/tests/test_db.py` (повністю):

```python
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from budget_bot.db import create_engine, create_readonly_engine


async def test_connect_pragmas_enable_wal_and_busy_timeout_on_a_real_file(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'pragmas.sqlite3'}")

    async with engine.connect() as connection:
        journal_mode = (await connection.execute(text("PRAGMA journal_mode"))).scalar()
        busy_timeout = (await connection.execute(text("PRAGMA busy_timeout"))).scalar()
        foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar()

    assert journal_mode == "wal"
    assert busy_timeout == 10000
    assert foreign_keys == 1

    await engine.dispose()


async def test_readonly_engine_rejects_writes_but_sees_the_bots_commits(tmp_path):
    path = tmp_path / "budget.sqlite3"
    writer = create_engine(f"sqlite+aiosqlite:///{path}")
    reader = create_readonly_engine(path)
    try:
        async with writer.begin() as connection:
            await connection.execute(text("CREATE TABLE t (x INTEGER)"))
            await connection.execute(text("INSERT INTO t VALUES (1)"))

        async with reader.connect() as connection:
            with pytest.raises(OperationalError, match="readonly database"):
                await connection.execute(text("INSERT INTO t VALUES (2)"))

        async with writer.begin() as connection:
            await connection.execute(text("INSERT INTO t VALUES (3)"))
        async with reader.connect() as connection:
            assert (await connection.execute(text("SELECT count(*) FROM t"))).scalar() == 2
    finally:
        await reader.dispose()
        await writer.dispose()


async def test_readonly_engine_reads_while_the_bot_holds_no_connection(tmp_path):
    path = tmp_path / "budget.sqlite3"
    writer = create_engine(f"sqlite+aiosqlite:///{path}")
    async with writer.begin() as connection:
        await connection.execute(text("CREATE TABLE t (x INTEGER)"))
        await connection.execute(text("INSERT INTO t VALUES (1)"))
    await writer.dispose()  # a clean close removes the WAL side files

    reader = create_readonly_engine(path)
    try:
        async with reader.connect() as connection:
            assert (await connection.execute(text("SELECT count(*) FROM t"))).scalar() == 1
    finally:
        await reader.dispose()
```

- [ ] **Step 3: Запустити — мають впасти**

Run: `.venv/bin/python -m pytest tests/test_periods.py tests/test_db.py -q`
Expected: помилки збору — `ImportError: cannot import name 'kyiv_day_range' from 'budget_bot.periods'` і `ImportError: cannot import name 'create_readonly_engine' from 'budget_bot.db'`.

- [ ] **Step 4: Реалізувати `kyiv_day_range`**

У `tg-bot/src/budget_bot/periods.py` додати перед `def period_range`:

```python
def kyiv_day_range(first: date, last: date, label: str = "") -> PeriodRange:
    """UTC-naive half-open range covering Kyiv calendar days ``first``..``last``, inclusive."""
    return PeriodRange(
        start=_kyiv_midnight_as_utc(first),
        end=_kyiv_midnight_as_utc(last + timedelta(days=1)),
        label=label,
    )


```

У кінці `period_range` замінити

```python
    return PeriodRange(
        start=_kyiv_midnight_as_utc(first),
        end=_kyiv_midnight_as_utc(last + timedelta(days=1)),
        label=label,
    )
```

на

```python
    return kyiv_day_range(first, last, label)
```

а в кінці `parse_custom_range` замінити

```python
    return PeriodRange(
        start=_kyiv_midnight_as_utc(first),
        end=_kyiv_midnight_as_utc(last + timedelta(days=1)),
        label=f"{first:%d.%m.%Y}–{last:%d.%m.%Y}",
    )
```

на

```python
    return kyiv_day_range(first, last, f"{first:%d.%m.%Y}–{last:%d.%m.%Y}")
```

- [ ] **Step 5: Реалізувати `create_readonly_engine`**

`tg-bot/src/budget_bot/db.py` (повністю):

```python
"""Async engine and session factory."""

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets readers and writers proceed concurrently instead of
        # blocking each other; it persists in the database file itself, so
        # only the first connection actually switches the mode, but setting
        # it on every connect is harmless. (An in-memory test DB reports
        # "memory" here regardless — that's SQLite's own behavior, not a
        # sign this isn't wired up.)
        cursor.execute("PRAGMA journal_mode=WAL")
        # A concurrent writer no longer surfaces "database is locked"
        # immediately — it waits up to this long for the lock instead.
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    return engine


def create_readonly_engine(database_path: Path) -> AsyncEngine:
    """Engine that can only read the bot's SQLite file (used by the Claude connector).

    Two independent guards: SQLite opens the file with ``mode=ro``, and every
    connection sets ``query_only``. No journal_mode pragma here — switching it
    is a write; the bot's engine has already put the file into WAL mode.
    """
    engine = create_async_engine(
        f"sqlite+aiosqlite:///file:{database_path}?mode=ro&uri=true", echo=False
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA query_only=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- [ ] **Step 6: Запустити — зелені, разом із наявними тестами періодів**

Run: `.venv/bin/python -m pytest -q`
Expected: усі тести проходять, зокрема наявні `test_parse_custom_range_*`, `test_week_*`, `test_month_range_crossing_dst_end`.

- [ ] **Step 7: Лінт**

Run: `.venv/bin/ruff check src tests && .venv/bin/black --check src tests`
Expected: без зауважень.

- [ ] **Step 8: Commit**

```bash
git add src/budget_bot/periods.py src/budget_bot/db.py tests/test_periods.py tests/test_db.py
git commit -m "feat: add Kyiv day ranges and a read-only SQLite engine"
```

---

### Task 2: Tool argument parsing

**Files:**
- Create: `tg-bot/src/budget_bot/connector/__init__.py`
- Create: `tg-bot/src/budget_bot/connector/inputs.py`
- Test: `tg-bot/tests/test_connector_inputs.py`

**Interfaces:**
- Consumes: —
- Produces (`budget_bot.connector.inputs`):
  - `class InvalidRequest(ValueError)` — помилка аргументів, яку викликач може виправити; її текст бачить модель.
  - `@dataclass(frozen=True) class DateRange: first: date; last: date` — київські дні, обидві межі включно.
  - `parse_date_range(start_date: str, end_date: str) -> DateRange`
  - `check_limit(limit: int) -> None`, `check_not_negative(name: str, value: int | None) -> None`
  - константи `MIN_YEAR = 2000`, `MAX_YEAR = 2100`, `MAX_LIST_LIMIT = 200`, `MAX_TREND_BUCKETS = 60`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_connector_inputs.py`:

```python
from datetime import date

import pytest

from budget_bot.connector.inputs import (
    DateRange,
    InvalidRequest,
    check_limit,
    check_not_negative,
    parse_date_range,
)


def test_parses_an_inclusive_range():
    assert parse_date_range("2026-09-01", "2026-09-14") == DateRange(
        date(2026, 9, 1), date(2026, 9, 14)
    )


def test_accepts_a_single_day_and_the_edges_of_supported_years():
    assert parse_date_range("2026-09-14", "2026-09-14") == DateRange(
        date(2026, 9, 14), date(2026, 9, 14)
    )
    assert parse_date_range("2000-01-01", "2100-12-31") == DateRange(
        date(2000, 1, 1), date(2100, 12, 31)
    )


@pytest.mark.parametrize(
    ("start_date", "end_date", "hint"),
    [
        ("14.09.2026", "2026-09-30", "start_date must be a valid calendar date in YYYY-MM-DD"),
        ("2026-09-01", "2026-02-30", "end_date must be a valid calendar date in YYYY-MM-DD"),
        ("1999-12-31", "2026-09-30", "start_date must be between 2000-01-01 and 2100-12-31"),
        ("2026-09-01", "2101-01-01", "end_date must be between 2000-01-01 and 2100-12-31"),
        ("2026-09-30", "2026-09-01", "end_date 2026-09-01 is before start_date 2026-09-30"),
    ],
)
def test_bad_ranges_are_rejected_with_a_hint(start_date, end_date, hint):
    with pytest.raises(InvalidRequest) as excinfo:
        parse_date_range(start_date, end_date)
    assert hint in str(excinfo.value)


@pytest.mark.parametrize("limit", [1, 200])
def test_limit_bounds_are_inclusive(limit):
    check_limit(limit)


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_outside_bounds_is_rejected(limit):
    with pytest.raises(InvalidRequest) as excinfo:
        check_limit(limit)
    assert f"limit must be between 1 and 200, got {limit}" in str(excinfo.value)


def test_negative_value_is_rejected_by_name():
    with pytest.raises(InvalidRequest) as excinfo:
        check_not_negative("offset", -1)
    assert "offset must be 0 or greater, got -1" in str(excinfo.value)


@pytest.mark.parametrize("value", [None, 0, 5])
def test_absent_zero_and_positive_values_pass(value):
    check_not_negative("min_amount", value)
```

- [ ] **Step 2: Запустити — має впасти**

Run: `.venv/bin/python -m pytest tests/test_connector_inputs.py -q`
Expected: `ModuleNotFoundError: No module named 'budget_bot.connector'`.

- [ ] **Step 3: Створити пакет**

`tg-bot/src/budget_bot/connector/__init__.py`:

```python
"""Read-only Claude connector: an MCP server over the bot's expense data."""
```

- [ ] **Step 4: Реалізувати розбір аргументів**

`tg-bot/src/budget_bot/connector/inputs.py`:

```python
"""Parsing and validation of connector tool arguments.

Everything here raises InvalidRequest with a message meant for the model: it
names the argument, says what was wrong and what a valid value looks like.
"""

from dataclasses import dataclass
from datetime import date, datetime

MIN_YEAR = 2000
MAX_YEAR = 2100
MAX_LIST_LIMIT = 200
MAX_TREND_BUCKETS = 60


class InvalidRequest(ValueError):
    """A problem with tool arguments that the caller can fix."""


@dataclass(frozen=True)
class DateRange:
    """Kyiv calendar days, both ends inclusive."""

    first: date
    last: date


def parse_date_range(start_date: str, end_date: str) -> DateRange:
    first = _parse_day("start_date", start_date)
    last = _parse_day("end_date", end_date)
    if last < first:
        raise InvalidRequest(
            f"end_date {last.isoformat()} is before start_date {first.isoformat()}"
        )
    return DateRange(first=first, last=last)


def check_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise InvalidRequest(f"limit must be between 1 and {MAX_LIST_LIMIT}, got {limit}")


def check_not_negative(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise InvalidRequest(f"{name} must be 0 or greater, got {value}")


def _parse_day(name: str, raw: str) -> date:
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise InvalidRequest(
            f"{name} must be a valid calendar date in YYYY-MM-DD format, got {raw!r}"
        ) from None
    if not MIN_YEAR <= day.year <= MAX_YEAR:
        raise InvalidRequest(
            f"{name} must be between {MIN_YEAR}-01-01 and {MAX_YEAR}-12-31, got {raw!r}"
        )
    return day
```

- [ ] **Step 5: Запустити — зелені**

Run: `.venv/bin/python -m pytest tests/test_connector_inputs.py -q`
Expected: усі проходять.

- [ ] **Step 6: Лінт**

Run: `.venv/bin/ruff check src tests && .venv/bin/black --check src tests`

- [ ] **Step 7: Commit**

```bash
git add src/budget_bot/connector/__init__.py src/budget_bot/connector/inputs.py tests/test_connector_inputs.py
git commit -m "feat: parse and validate Claude connector tool arguments"
```

---

### Task 3: Budget overview and spending summary

**Files:**
- Modify: `tg-bot/tests/conftest.py`
- Create: `tg-bot/src/budget_bot/connector/schemas.py`
- Create: `tg-bot/src/budget_bot/connector/analytics.py`
- Test: `tg-bot/tests/test_connector_summary.py`

**Interfaces:**
- Consumes: `kyiv_day_range`, `create_readonly_engine` (Task 1); `DateRange`, `InvalidRequest` (Task 2); наявні `list_members`, `list_categories`, `normalize_category_name`, `SINGLETON_HOUSEHOLD_ID`, `create_expense`, `to_kyiv`, `KYIV`.
- Produces:
  - `budget_bot.connector.schemas`: `CategoryInfo(name, is_custom)`, `BudgetOverview(today, timezone, currency, members: list[str], categories: list[CategoryInfo], first_expense_date, last_expense_date, expense_count)`, `CategorySpending(name, amount, share_percent, count)`, `MemberSpending(name, amount, count)`, `SpendingSummary(start_date, end_date, category: str | None, member: str | None, total, expense_count, by_category, by_member)`.
  - `budget_bot.connector.analytics`:
    - `find_category(session, name: str | None) -> Category | None` і `find_member(session, name: str | None) -> Member | None` — без урахування регістру; невідома чи неоднозначна назва → `InvalidRequest` зі списком наявних.
    - `budget_overview(session, now_utc: datetime) -> BudgetOverview`
    - `summarize_spending(session, date_range: DateRange, *, category: Category | None, member: Member | None) -> SpendingSummary`
    - приватний `_conditions(date_range, category, member) -> list[ColumnElement[bool]]` — ним користуються Tasks 4 і 5.
  - `tests/conftest.py`: `kyiv(year, month, day, hour=12, minute=0) -> datetime` (київський час → UTC-naive), фікстури `budget_db -> Path`, `budget_writer -> BudgetWriter` (`add_expense(*, category, member, amount, at, description=None)`, `add_member(display_name, telegram_id)`), `early_september` (5 витрат, таблиця в докстрінгу), `readonly_session_factory`.

- [ ] **Step 1: Додати фікстури справжньої БД у `conftest.py`**

У `tg-bot/tests/conftest.py` замінити блок імпортів (усе до першого `@pytest_asyncio.fixture`) на:

```python
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
```

і додати в кінець файлу:

```python


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
```

- [ ] **Step 2: Написати падаючий тест**

`tg-bot/tests/test_connector_summary.py`:

```python
from datetime import date, datetime

import pytest

from budget_bot.connector.analytics import (
    budget_overview,
    find_category,
    find_member,
    summarize_spending,
)
from budget_bot.connector.inputs import DateRange, InvalidRequest
from budget_bot.connector.schemas import CategorySpending, MemberSpending
from budget_bot.periods import kyiv_day_range
from budget_bot.services.access import SINGLETON_HOUSEHOLD_ID
from budget_bot.services.reports import build_report

SEPTEMBER_1_TO_14 = DateRange(date(2026, 9, 1), date(2026, 9, 14))
DEFAULT_CATEGORY_NAMES = [
    "Їжа",
    "Транспорт",
    "Комунальні",
    "Оренда житла",
    "Розваги",
    "Здоров'я",
    "Одяг",
    "Діти",
    "Інше",
]


@pytest.mark.parametrize("name", ["Їжа", "їжа", "  ЇЖА "])
async def test_category_is_found_ignoring_case_and_spacing(readonly_session_factory, name):
    async with readonly_session_factory() as session:
        category = await find_category(session, name)
    assert category.name == "Їжа"


async def test_member_is_found_ignoring_case(readonly_session_factory):
    async with readonly_session_factory() as session:
        member = await find_member(session, "ОЛЯ")
    assert member.display_name == "Оля"


async def test_no_name_means_no_filter(readonly_session_factory):
    async with readonly_session_factory() as session:
        assert await find_category(session, None) is None
        assert await find_member(session, None) is None


async def test_unknown_category_lists_the_known_ones(readonly_session_factory):
    async with readonly_session_factory() as session:
        with pytest.raises(InvalidRequest) as excinfo:
            await find_category(session, "Кава")
    message = str(excinfo.value)
    assert "Unknown category 'Кава'" in message
    assert "Known categories: Їжа, Транспорт, Комунальні" in message


async def test_unknown_member_lists_the_known_ones(readonly_session_factory):
    async with readonly_session_factory() as session:
        with pytest.raises(InvalidRequest) as excinfo:
            await find_member(session, "Петро")
    assert "Unknown member 'Петро'. Known members: Сергій, Оля" in str(excinfo.value)


async def test_member_names_differing_only_by_case_are_ambiguous(
    budget_writer, readonly_session_factory
):
    await budget_writer.add_member("ОЛЯ", telegram_id=333)
    async with readonly_session_factory() as session:
        with pytest.raises(InvalidRequest) as excinfo:
            await find_member(session, "оля")
    assert "ambiguous" in str(excinfo.value)


async def test_overview_describes_the_data(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        # 22:30 UTC on the 14th is already 01:30 on the 15th in Kyiv.
        overview = await budget_overview(session, now_utc=datetime(2026, 9, 14, 22, 30))

    assert overview.today == date(2026, 9, 15)
    assert (overview.timezone, overview.currency) == ("Europe/Kyiv", "UAH")
    assert overview.members == ["Сергій", "Оля"]
    assert [c.name for c in overview.categories] == DEFAULT_CATEGORY_NAMES
    assert not any(c.is_custom for c in overview.categories)
    assert overview.expense_count == 5
    assert overview.first_expense_date == date(2026, 8, 31)
    # Expense 4 is 21:10 UTC on the 14th, but the 15th in Kyiv.
    assert overview.last_expense_date == date(2026, 9, 15)


async def test_overview_without_expenses(readonly_session_factory):
    async with readonly_session_factory() as session:
        overview = await budget_overview(session, now_utc=datetime(2026, 9, 14, 12, 0))
    assert overview.expense_count == 0
    assert (overview.first_expense_date, overview.last_expense_date) == (None, None)


async def test_summary_totals_and_breakdowns(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(session, SEPTEMBER_1_TO_14, category=None, member=None)

    assert (summary.start_date, summary.end_date) == (date(2026, 9, 1), date(2026, 9, 14))
    assert (summary.category, summary.member) == (None, None)
    assert summary.total == 1550
    assert summary.expense_count == 3
    assert summary.by_category == [
        CategorySpending(name="Їжа", amount=1450, share_percent=93.5, count=2),
        CategorySpending(name="Транспорт", amount=100, share_percent=6.5, count=1),
    ]
    assert summary.by_member == [
        MemberSpending(name="Оля", amount=1300, count=2),
        MemberSpending(name="Сергій", amount=250, count=1),
    ]


@pytest.mark.parametrize(
    ("day", "total"),
    [
        (date(2026, 9, 14), 1200),  # 23:30 Kyiv still belongs to the 14th
        (date(2026, 9, 15), 600),  # 00:10 Kyiv belongs to the 15th, though UTC says the 14th
        (date(2026, 8, 31), 350),
    ],
)
async def test_days_are_kyiv_calendar_days(early_september, readonly_session_factory, day, total):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(session, DateRange(day, day), category=None, member=None)
    assert summary.total == total


async def test_summary_narrowed_to_a_category_and_a_member(
    early_september, readonly_session_factory
):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(
            session,
            SEPTEMBER_1_TO_14,
            category=await find_category(session, "їжа"),
            member=await find_member(session, "оля"),
        )
    assert (summary.category, summary.member) == ("Їжа", "Оля")
    assert summary.total == 1200
    assert summary.by_member == [MemberSpending(name="Оля", amount=1200, count=1)]


async def test_empty_range_is_zero_not_an_error(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(
            session, DateRange(date(2026, 7, 1), date(2026, 7, 31)), category=None, member=None
        )
    assert (summary.total, summary.expense_count) == (0, 0)
    assert (summary.by_category, summary.by_member) == ([], [])


async def test_summary_agrees_with_the_bots_report(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(session, SEPTEMBER_1_TO_14, category=None, member=None)
        report = await build_report(
            session, SINGLETON_HOUSEHOLD_ID, kyiv_day_range(date(2026, 9, 1), date(2026, 9, 14))
        )
    assert summary.total == report.total
    assert [(c.name, c.amount, c.share_percent) for c in summary.by_category] == [
        (c.name, c.amount, c.share) for c in report.by_category
    ]
    assert [(m.name, m.amount) for m in summary.by_member] == [
        (m.display_name, m.amount) for m in report.by_member
    ]
```

Очікування пораховано вручну з таблиці `early_september`: за 1–14 вересня входять витрати 1, 2, 3 → `250 + 100 + 1200 = 1550`; Їжа `1450` = 93.548…% → `93.5`; Транспорт `100` = 6.45…% → `6.5`.

- [ ] **Step 3: Запустити — має впасти**

Run: `.venv/bin/python -m pytest tests/test_connector_summary.py -q`
Expected: `ModuleNotFoundError: No module named 'budget_bot.connector.analytics'`.

- [ ] **Step 4: Створити моделі відповідей**

`tg-bot/src/budget_bot/connector/schemas.py`:

```python
"""Pydantic models returned by the connector tools — the public API contract.

The MCP SDK publishes them as each tool's output schema and sends results as
structured content, so field names and meanings must stay stable.
"""

import datetime as dt

from pydantic import BaseModel, Field


class CategoryInfo(BaseModel):
    name: str
    is_custom: bool = Field(description="False for the bot's default categories")


class BudgetOverview(BaseModel):
    today: dt.date = Field(description="Today's date in Europe/Kyiv")
    timezone: str
    currency: str
    members: list[str]
    categories: list[CategoryInfo]
    first_expense_date: dt.date | None = Field(description="Kyiv date of the earliest expense")
    last_expense_date: dt.date | None = Field(description="Kyiv date of the latest expense")
    expense_count: int


class CategorySpending(BaseModel):
    name: str
    amount: int
    share_percent: float = Field(description="Share of the total in percent, one decimal")
    count: int


class MemberSpending(BaseModel):
    name: str
    amount: int
    count: int


class SpendingSummary(BaseModel):
    start_date: dt.date
    end_date: dt.date
    category: str | None
    member: str | None
    total: int
    expense_count: int
    by_category: list[CategorySpending]
    by_member: list[MemberSpending]
```

- [ ] **Step 5: Реалізувати аналітику**

`tg-bot/src/budget_bot/connector/analytics.py`:

```python
"""Read-only spending analytics behind the Claude connector tools.

Each function takes an AsyncSession plus already-validated arguments and
returns a model from schemas.py. Anything grouped by Kyiv calendar day is
grouped in Python: SQLite knows nothing about Europe/Kyiv or its DST switches.
"""

from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.connector.inputs import DateRange, InvalidRequest
from budget_bot.connector.schemas import (
    BudgetOverview,
    CategoryInfo,
    CategorySpending,
    MemberSpending,
    SpendingSummary,
)
from budget_bot.models import Category, Expense, Member
from budget_bot.periods import kyiv_day_range, to_kyiv
from budget_bot.services.access import SINGLETON_HOUSEHOLD_ID, list_members
from budget_bot.services.categories import list_categories, normalize_category_name

HOUSEHOLD_ID = SINGLETON_HOUSEHOLD_ID
TIMEZONE = "Europe/Kyiv"
CURRENCY = "UAH"


async def find_category(session: AsyncSession, name: str | None) -> Category | None:
    """Resolve a category by name, ignoring case and extra spaces; None means no filter."""
    if name is None:
        return None
    categories = await list_categories(session, HOUSEHOLD_ID)
    wanted = normalize_category_name(name)
    for category in categories:
        if category.name_normalized == wanted:
            return category
    known = ", ".join(category.name for category in categories) or "none yet"
    raise InvalidRequest(f"Unknown category {name!r}. Known categories: {known}")


async def find_member(session: AsyncSession, name: str | None) -> Member | None:
    """Resolve a member by display name, ignoring case and extra spaces; None means no filter."""
    if name is None:
        return None
    members = await list_members(session, HOUSEHOLD_ID)
    # Same folding as category names: SQLite's LOWER() would not fold Cyrillic.
    wanted = normalize_category_name(name)
    matches = [m for m in members if normalize_category_name(m.display_name) == wanted]
    known = ", ".join(member.display_name for member in members) or "none yet"
    if not matches:
        raise InvalidRequest(f"Unknown member {name!r}. Known members: {known}")
    if len(matches) > 1:
        raise InvalidRequest(f"Member name {name!r} is ambiguous. Known members: {known}")
    return matches[0]


async def budget_overview(session: AsyncSession, now_utc: datetime) -> BudgetOverview:
    members = await list_members(session, HOUSEHOLD_ID)
    categories = await list_categories(session, HOUSEHOLD_ID)
    count, first, last = (
        await session.execute(
            select(
                func.count(Expense.id), func.min(Expense.created_at), func.max(Expense.created_at)
            ).where(Expense.household_id == HOUSEHOLD_ID)
        )
    ).one()
    return BudgetOverview(
        today=to_kyiv(now_utc).date(),
        timezone=TIMEZONE,
        currency=CURRENCY,
        members=[member.display_name for member in members],
        categories=[CategoryInfo(name=c.name, is_custom=c.is_custom) for c in categories],
        first_expense_date=to_kyiv(first).date() if first is not None else None,
        last_expense_date=to_kyiv(last).date() if last is not None else None,
        expense_count=count,
    )


async def summarize_spending(
    session: AsyncSession,
    date_range: DateRange,
    *,
    category: Category | None,
    member: Member | None,
) -> SpendingSummary:
    conditions = _conditions(date_range, category, member)
    amount = func.sum(Expense.amount)
    category_rows = (
        await session.execute(
            select(Category.name, amount, func.count(Expense.id))
            .join(Category, Category.id == Expense.category_id)
            .where(*conditions)
            .group_by(Category.id, Category.name)
            .order_by(amount.desc(), Category.name)
        )
    ).all()
    member_rows = (
        await session.execute(
            select(Member.display_name, amount, func.count(Expense.id))
            .join(Member, Member.id == Expense.member_id)
            .where(*conditions)
            .group_by(Member.id, Member.display_name)
            .order_by(amount.desc(), Member.display_name)
        )
    ).all()

    total = sum(row[1] for row in category_rows)
    return SpendingSummary(
        start_date=date_range.first,
        end_date=date_range.last,
        category=category.name if category is not None else None,
        member=member.display_name if member is not None else None,
        total=total,
        expense_count=sum(row[2] for row in category_rows),
        by_category=[
            CategorySpending(
                name=name, amount=value, share_percent=round(value * 100 / total, 1), count=n
            )
            for name, value, n in category_rows
        ],
        by_member=[
            MemberSpending(name=name, amount=value, count=n) for name, value, n in member_rows
        ],
    )


def _conditions(
    date_range: DateRange, category: Category | None, member: Member | None
) -> list[ColumnElement[bool]]:
    period = kyiv_day_range(date_range.first, date_range.last)
    conditions = [
        Expense.household_id == HOUSEHOLD_ID,
        Expense.created_at >= period.start,
        Expense.created_at < period.end,
    ]
    if category is not None:
        conditions.append(Expense.category_id == category.id)
    if member is not None:
        conditions.append(Expense.member_id == member.id)
    return conditions
```

- [ ] **Step 6: Запустити — зелені**

Run: `.venv/bin/python -m pytest tests/test_connector_summary.py -q`
Expected: усі проходять.

- [ ] **Step 7: Повний набір і лінт**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

- [ ] **Step 8: Commit**

```bash
git add tests/conftest.py src/budget_bot/connector/schemas.py src/budget_bot/connector/analytics.py tests/test_connector_summary.py
git commit -m "feat: budget overview and spending summary for the Claude connector"
```

---

### Task 4: Spending trend

**Files:**
- Modify: `tg-bot/src/budget_bot/connector/schemas.py`
- Modify: `tg-bot/src/budget_bot/connector/analytics.py`
- Test: `tg-bot/tests/test_connector_trend.py`

**Interfaces:**
- Consumes: `_conditions`, `find_member` (Task 3); `DateRange`, `InvalidRequest`, `MAX_TREND_BUCKETS` (Task 2); `to_kyiv`.
- Produces:
  - `budget_bot.connector.schemas`: `Granularity = Literal["week", "month"]`, `SplitBy = Literal["none", "category", "member"]`, `BreakdownItem(name, amount, count)`, `TrendBucket(start_date, end_date, partial, total, count, breakdown: list[BreakdownItem] | None)`, `SpendingTrend(start_date, end_date, granularity, split_by, category, member, buckets)`.
  - `budget_bot.connector.analytics`:
    - `@dataclass(frozen=True) class BucketSpan: first: date; last: date; partial: bool`
    - `trend_buckets(date_range: DateRange, granularity: Granularity) -> list[BucketSpan]` — понад 60 кошиків → `InvalidRequest`.
    - `spending_trend(session, date_range, *, granularity: Granularity, split_by: SplitBy, category: Category | None, member: Member | None) -> SpendingTrend`

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_connector_trend.py`:

```python
from datetime import date

import pytest

from budget_bot.connector.analytics import (
    BucketSpan,
    find_member,
    spending_trend,
    trend_buckets,
)
from budget_bot.connector.inputs import DateRange, InvalidRequest
from budget_bot.connector.schemas import BreakdownItem, TrendBucket
from tests.conftest import kyiv

SEPTEMBER_1_TO_14 = DateRange(date(2026, 9, 1), date(2026, 9, 14))


def test_weeks_run_monday_to_sunday_and_clipped_edges_are_partial():
    # 1 September 2026 is a Tuesday, 14 September a Monday.
    assert trend_buckets(SEPTEMBER_1_TO_14, "week") == [
        BucketSpan(date(2026, 9, 1), date(2026, 9, 6), partial=True),
        BucketSpan(date(2026, 9, 7), date(2026, 9, 13), partial=False),
        BucketSpan(date(2026, 9, 14), date(2026, 9, 14), partial=True),
    ]


def test_months_are_calendar_months():
    assert trend_buckets(DateRange(date(2026, 1, 15), date(2026, 3, 31)), "month") == [
        BucketSpan(date(2026, 1, 15), date(2026, 1, 31), partial=True),
        BucketSpan(date(2026, 2, 1), date(2026, 2, 28), partial=False),
        BucketSpan(date(2026, 3, 1), date(2026, 3, 31), partial=False),
    ]


def test_sixty_buckets_are_allowed():
    assert len(trend_buckets(DateRange(date(2021, 1, 1), date(2025, 12, 31)), "month")) == 60


@pytest.mark.parametrize(
    ("date_range", "granularity", "hint"),
    [
        (
            DateRange(date(2025, 1, 1), date(2026, 12, 31)),
            "week",
            'gives 105 week buckets (max 60); use granularity="month" or a shorter date range',
        ),
        (
            DateRange(date(2021, 1, 1), date(2026, 1, 1)),
            "month",
            "gives 61 month buckets (max 60); use a shorter date range",
        ),
    ],
)
def test_too_many_buckets_are_rejected_with_a_hint(date_range, granularity, hint):
    with pytest.raises(InvalidRequest) as excinfo:
        trend_buckets(date_range, granularity)
    assert hint in str(excinfo.value)


async def test_weekly_trend_split_by_category(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        trend = await spending_trend(
            session,
            SEPTEMBER_1_TO_14,
            granularity="week",
            split_by="category",
            category=None,
            member=None,
        )
    assert trend.buckets == [
        TrendBucket(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 6),
            partial=True,
            total=350,
            count=2,
            breakdown=[
                BreakdownItem(name="Їжа", amount=250, count=1),
                BreakdownItem(name="Транспорт", amount=100, count=1),
            ],
        ),
        TrendBucket(
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 13),
            partial=False,
            total=0,
            count=0,
            breakdown=[],
        ),
        TrendBucket(
            start_date=date(2026, 9, 14),
            end_date=date(2026, 9, 14),
            partial=True,
            total=1200,
            count=1,
            breakdown=[BreakdownItem(name="Їжа", amount=1200, count=1)],
        ),
    ]


async def test_split_by_member_and_no_split(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        by_member = await spending_trend(
            session,
            SEPTEMBER_1_TO_14,
            granularity="week",
            split_by="member",
            category=None,
            member=None,
        )
        unsplit = await spending_trend(
            session,
            SEPTEMBER_1_TO_14,
            granularity="week",
            split_by="none",
            category=None,
            member=None,
        )
    assert by_member.buckets[0].breakdown == [
        BreakdownItem(name="Сергій", amount=250, count=1),
        BreakdownItem(name="Оля", amount=100, count=1),
    ]
    assert [b.total for b in unsplit.buckets] == [350, 0, 1200]
    assert [b.breakdown for b in unsplit.buckets] == [None, None, None]


async def test_monthly_trend_for_one_member(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        trend = await spending_trend(
            session,
            DateRange(date(2026, 8, 1), date(2026, 9, 30)),
            granularity="month",
            split_by="none",
            category=None,
            member=await find_member(session, "Сергій"),
        )
    assert trend.member == "Сергій"
    assert [(b.start_date, b.end_date, b.partial, b.total, b.count) for b in trend.buckets] == [
        (date(2026, 8, 1), date(2026, 8, 31), False, 350, 1),
        (date(2026, 9, 1), date(2026, 9, 30), False, 850, 2),
    ]


async def test_week_boundary_follows_kyiv_time_across_the_dst_switch(
    budget_writer, readonly_session_factory
):
    # Kyiv leaves summer time at 04:00 on Sunday 25 October 2026 (UTC+3 -> UTC+2).
    # Both expenses fall on 25 October in UTC but in different Kyiv weeks.
    await budget_writer.add_expense(
        category="Їжа", member="Сергій", amount=300, at=kyiv(2026, 10, 25, 23, 30)
    )
    await budget_writer.add_expense(
        category="Їжа", member="Оля", amount=200, at=kyiv(2026, 10, 26, 0, 30)
    )
    async with readonly_session_factory() as session:
        trend = await spending_trend(
            session,
            DateRange(date(2026, 10, 19), date(2026, 10, 26)),
            granularity="week",
            split_by="none",
            category=None,
            member=None,
        )
    assert [(b.start_date, b.end_date, b.partial, b.total) for b in trend.buckets] == [
        (date(2026, 10, 19), date(2026, 10, 25), False, 300),
        (date(2026, 10, 26), date(2026, 10, 26), True, 200),
    ]
```

- [ ] **Step 2: Запустити — має впасти**

Run: `.venv/bin/python -m pytest tests/test_connector_trend.py -q`
Expected: `ImportError: cannot import name 'BucketSpan' from 'budget_bot.connector.analytics'`.

- [ ] **Step 3: Розширити моделі**

`tg-bot/src/budget_bot/connector/schemas.py` (повністю):

```python
"""Pydantic models returned by the connector tools — the public API contract.

The MCP SDK publishes them as each tool's output schema and sends results as
structured content, so field names and meanings must stay stable.
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Granularity = Literal["week", "month"]
SplitBy = Literal["none", "category", "member"]


class CategoryInfo(BaseModel):
    name: str
    is_custom: bool = Field(description="False for the bot's default categories")


class BudgetOverview(BaseModel):
    today: dt.date = Field(description="Today's date in Europe/Kyiv")
    timezone: str
    currency: str
    members: list[str]
    categories: list[CategoryInfo]
    first_expense_date: dt.date | None = Field(description="Kyiv date of the earliest expense")
    last_expense_date: dt.date | None = Field(description="Kyiv date of the latest expense")
    expense_count: int


class CategorySpending(BaseModel):
    name: str
    amount: int
    share_percent: float = Field(description="Share of the total in percent, one decimal")
    count: int


class MemberSpending(BaseModel):
    name: str
    amount: int
    count: int


class SpendingSummary(BaseModel):
    start_date: dt.date
    end_date: dt.date
    category: str | None
    member: str | None
    total: int
    expense_count: int
    by_category: list[CategorySpending]
    by_member: list[MemberSpending]


class BreakdownItem(BaseModel):
    name: str
    amount: int
    count: int


class TrendBucket(BaseModel):
    start_date: dt.date
    end_date: dt.date
    partial: bool = Field(description="True when the date range cuts this week or month short")
    total: int
    count: int
    breakdown: list[BreakdownItem] | None


class SpendingTrend(BaseModel):
    start_date: dt.date
    end_date: dt.date
    granularity: Granularity
    split_by: SplitBy
    category: str | None
    member: str | None
    buckets: list[TrendBucket]
```

- [ ] **Step 4: Розширити аналітику**

У `tg-bot/src/budget_bot/connector/analytics.py` замінити блок імпортів (від `from datetime import datetime` до `from budget_bot.services.categories import …` включно) на:

```python
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.connector.inputs import MAX_TREND_BUCKETS, DateRange, InvalidRequest
from budget_bot.connector.schemas import (
    BreakdownItem,
    BudgetOverview,
    CategoryInfo,
    CategorySpending,
    Granularity,
    MemberSpending,
    SpendingSummary,
    SpendingTrend,
    SplitBy,
    TrendBucket,
)
from budget_bot.models import Category, Expense, Member
from budget_bot.periods import kyiv_day_range, to_kyiv
from budget_bot.services.access import SINGLETON_HOUSEHOLD_ID, list_members
from budget_bot.services.categories import list_categories, normalize_category_name
```

і додати в кінець файлу:

```python


@dataclass(frozen=True)
class BucketSpan:
    first: date
    last: date
    partial: bool


def trend_buckets(date_range: DateRange, granularity: Granularity) -> list[BucketSpan]:
    """Weeks (Monday–Sunday) or calendar months covering the range, clipped to it."""
    count = _bucket_count(date_range, granularity)
    if count > MAX_TREND_BUCKETS:
        hint = (
            'use granularity="month" or a shorter date range'
            if granularity == "week"
            else "use a shorter date range"
        )
        raise InvalidRequest(
            f"{date_range.first.isoformat()}..{date_range.last.isoformat()} gives {count} "
            f"{granularity} buckets (max {MAX_TREND_BUCKETS}); {hint}"
        )

    spans = []
    start = _bucket_start(date_range.first, granularity)
    while start <= date_range.last:
        end = _bucket_end(start, granularity)
        first = max(start, date_range.first)
        last = min(end, date_range.last)
        spans.append(BucketSpan(first=first, last=last, partial=(first, last) != (start, end)))
        start = end + timedelta(days=1)
    return spans


async def spending_trend(
    session: AsyncSession,
    date_range: DateRange,
    *,
    granularity: Granularity,
    split_by: SplitBy,
    category: Category | None,
    member: Member | None,
) -> SpendingTrend:
    spans = trend_buckets(date_range, granularity)
    rows = (
        await session.execute(
            select(Expense.created_at, Expense.amount, Category.name, Member.display_name)
            .join(Category, Category.id == Expense.category_id)
            .join(Member, Member.id == Expense.member_id)
            .where(*_conditions(date_range, category, member))
        )
    ).all()

    starts = [span.first for span in spans]
    totals = [0] * len(spans)
    counts = [0] * len(spans)
    groups: list[defaultdict[str, list[int]]] = [defaultdict(lambda: [0, 0]) for _ in spans]
    for created_at, amount, category_name, member_name in rows:
        index = bisect_right(starts, to_kyiv(created_at).date()) - 1
        totals[index] += amount
        counts[index] += 1
        if split_by != "none":
            entry = groups[index][category_name if split_by == "category" else member_name]
            entry[0] += amount
            entry[1] += 1

    return SpendingTrend(
        start_date=date_range.first,
        end_date=date_range.last,
        granularity=granularity,
        split_by=split_by,
        category=category.name if category is not None else None,
        member=member.display_name if member is not None else None,
        buckets=[
            TrendBucket(
                start_date=span.first,
                end_date=span.last,
                partial=span.partial,
                total=totals[index],
                count=counts[index],
                breakdown=None if split_by == "none" else _breakdown(groups[index]),
            )
            for index, span in enumerate(spans)
        ],
    )


def _bucket_start(day: date, granularity: Granularity) -> date:
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def _bucket_end(start: date, granularity: Granularity) -> date:
    if granularity == "week":
        return start + timedelta(days=6)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def _bucket_count(date_range: DateRange, granularity: Granularity) -> int:
    if granularity == "week":
        first_week = _bucket_start(date_range.first, "week")
        last_week = _bucket_start(date_range.last, "week")
        return (last_week - first_week).days // 7 + 1
    first, last = date_range.first, date_range.last
    return (last.year - first.year) * 12 + last.month - first.month + 1


def _breakdown(group: dict[str, list[int]]) -> list[BreakdownItem]:
    ordered = sorted(group.items(), key=lambda item: (-item[1][0], item[0]))
    return [BreakdownItem(name=name, amount=amount, count=n) for name, (amount, n) in ordered]
```

- [ ] **Step 5: Запустити — зелені**

Run: `.venv/bin/python -m pytest tests/test_connector_trend.py tests/test_connector_summary.py -q`
Expected: усі проходять.

- [ ] **Step 6: Повний набір і лінт**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

- [ ] **Step 7: Commit**

```bash
git add src/budget_bot/connector/schemas.py src/budget_bot/connector/analytics.py tests/test_connector_trend.py
git commit -m "feat: weekly and monthly spending trend for the Claude connector"
```

---

### Task 5: Expense list

**Files:**
- Modify: `tg-bot/src/budget_bot/connector/schemas.py`
- Modify: `tg-bot/src/budget_bot/connector/analytics.py`
- Test: `tg-bot/tests/test_connector_list.py`

**Interfaces:**
- Consumes: `_conditions`, `find_category`, `find_member` (Task 3); `DateRange` (Task 2); `to_kyiv`.
- Produces:
  - `budget_bot.connector.schemas`: `SortOrder = Literal["newest", "oldest", "largest"]`, `ExpenseItem(id, datetime, amount, category, member, description)`, `ExpensePage(items, total_count, offset, next_offset: int | None)`.
  - `budget_bot.connector.analytics.list_expenses(session, date_range, *, category: Category | None, member: Member | None, search: str | None, min_amount: int | None, sort: SortOrder, limit: int, offset: int) -> ExpensePage`

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_connector_list.py`:

```python
from datetime import date

import pytest

from budget_bot.connector.analytics import find_category, find_member, list_expenses
from budget_bot.connector.inputs import DateRange
from budget_bot.connector.schemas import ExpensePage

ALL_DAYS = DateRange(date(2026, 8, 31), date(2026, 9, 15))


async def list_page(session_factory, **overrides) -> ExpensePage:
    arguments = {
        "date_range": ALL_DAYS,
        "category": None,
        "member": None,
        "search": None,
        "min_amount": None,
        "sort": "newest",
        "limit": 50,
        "offset": 0,
    } | overrides
    date_range = arguments.pop("date_range")
    async with session_factory() as session:
        return await list_expenses(session, date_range, **arguments)


@pytest.mark.parametrize(
    ("sort", "amounts"),
    [
        ("newest", [600, 1200, 100, 250, 350]),
        ("oldest", [350, 250, 100, 1200, 600]),
        ("largest", [1200, 600, 350, 250, 100]),
    ],
)
async def test_sort_orders(early_september, readonly_session_factory, sort, amounts):
    page = await list_page(readonly_session_factory, sort=sort)
    assert [item.amount for item in page.items] == amounts
    assert page.total_count == 5


async def test_items_carry_the_bot_id_kyiv_time_and_names(
    early_september, readonly_session_factory
):
    page = await list_page(
        readonly_session_factory, date_range=DateRange(date(2026, 9, 14), date(2026, 9, 14))
    )
    assert [item.model_dump(mode="json") for item in page.items] == [
        {
            "id": 3,
            "datetime": "2026-09-14T23:30:00+03:00",
            "amount": 1200,
            "category": "Їжа",
            "member": "Оля",
            "description": "Сільпо",
        }
    ]


async def test_search_ignores_case_in_cyrillic(early_september, readonly_session_factory):
    page = await list_page(readonly_session_factory, search="ТАКСІ")
    assert [item.description for item in page.items] == ["Таксі додому"]
    assert page.total_count == 1


async def test_min_amount_is_inclusive(early_september, readonly_session_factory):
    page = await list_page(readonly_session_factory, min_amount=350)
    assert [item.amount for item in page.items] == [600, 1200, 350]


async def test_category_and_member_filters(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        food = await find_category(session, "Їжа")
        serhii = await find_member(session, "Сергій")
    page = await list_page(readonly_session_factory, category=food, member=serhii)
    assert [item.amount for item in page.items] == [250, 350]


@pytest.mark.parametrize(
    ("offset", "amounts", "next_offset"),
    [(0, [600, 1200], 2), (2, [100, 250], 4), (4, [350], None), (6, [], None)],
)
async def test_pages(early_september, readonly_session_factory, offset, amounts, next_offset):
    page = await list_page(readonly_session_factory, limit=2, offset=offset)
    assert [item.amount for item in page.items] == amounts
    assert (page.total_count, page.offset, page.next_offset) == (5, offset, next_offset)


async def test_total_count_is_taken_after_search(early_september, readonly_session_factory):
    # "к" occurs in "кава", "Таксі додому" and "Кіно"; expense 5 has no description.
    page = await list_page(readonly_session_factory, search="к", limit=1)
    assert (len(page.items), page.total_count, page.next_offset) == (1, 3, 1)
```

- [ ] **Step 2: Запустити — має впасти**

Run: `.venv/bin/python -m pytest tests/test_connector_list.py -q`
Expected: `ImportError: cannot import name 'list_expenses' from 'budget_bot.connector.analytics'`.

- [ ] **Step 3: Розширити моделі**

`tg-bot/src/budget_bot/connector/schemas.py` (повністю):

```python
"""Pydantic models returned by the connector tools — the public API contract.

The MCP SDK publishes them as each tool's output schema and sends results as
structured content, so field names and meanings must stay stable.
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Granularity = Literal["week", "month"]
SplitBy = Literal["none", "category", "member"]
SortOrder = Literal["newest", "oldest", "largest"]


class CategoryInfo(BaseModel):
    name: str
    is_custom: bool = Field(description="False for the bot's default categories")


class BudgetOverview(BaseModel):
    today: dt.date = Field(description="Today's date in Europe/Kyiv")
    timezone: str
    currency: str
    members: list[str]
    categories: list[CategoryInfo]
    first_expense_date: dt.date | None = Field(description="Kyiv date of the earliest expense")
    last_expense_date: dt.date | None = Field(description="Kyiv date of the latest expense")
    expense_count: int


class CategorySpending(BaseModel):
    name: str
    amount: int
    share_percent: float = Field(description="Share of the total in percent, one decimal")
    count: int


class MemberSpending(BaseModel):
    name: str
    amount: int
    count: int


class SpendingSummary(BaseModel):
    start_date: dt.date
    end_date: dt.date
    category: str | None
    member: str | None
    total: int
    expense_count: int
    by_category: list[CategorySpending]
    by_member: list[MemberSpending]


class BreakdownItem(BaseModel):
    name: str
    amount: int
    count: int


class TrendBucket(BaseModel):
    start_date: dt.date
    end_date: dt.date
    partial: bool = Field(description="True when the date range cuts this week or month short")
    total: int
    count: int
    breakdown: list[BreakdownItem] | None


class SpendingTrend(BaseModel):
    start_date: dt.date
    end_date: dt.date
    granularity: Granularity
    split_by: SplitBy
    category: str | None
    member: str | None
    buckets: list[TrendBucket]


class ExpenseItem(BaseModel):
    id: int = Field(description="The number the bot shows as «Витрата #N»")
    datetime: dt.datetime = Field(description="When the expense was recorded, Kyiv time")
    amount: int
    category: str
    member: str = Field(description="Who recorded the expense")
    description: str | None


class ExpensePage(BaseModel):
    items: list[ExpenseItem]
    total_count: int
    offset: int
    next_offset: int | None = Field(description="Offset of the next page; null on the last page")
```

- [ ] **Step 4: Розширити аналітику**

У `tg-bot/src/budget_bot/connector/analytics.py` замінити блок імпортів (від `from bisect import bisect_right` до `from budget_bot.services.categories import …` включно) на:

```python
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.connector.inputs import MAX_TREND_BUCKETS, DateRange, InvalidRequest
from budget_bot.connector.schemas import (
    BreakdownItem,
    BudgetOverview,
    CategoryInfo,
    CategorySpending,
    ExpenseItem,
    ExpensePage,
    Granularity,
    MemberSpending,
    SortOrder,
    SpendingSummary,
    SpendingTrend,
    SplitBy,
    TrendBucket,
)
from budget_bot.models import Category, Expense, Member
from budget_bot.periods import kyiv_day_range, to_kyiv
from budget_bot.services.access import SINGLETON_HOUSEHOLD_ID, list_members
from budget_bot.services.categories import list_categories, normalize_category_name
```

і додати в кінець файлу:

```python


_SORTS = {
    "newest": (lambda row: (row.created_at, row.id), True),
    "oldest": (lambda row: (row.created_at, row.id), False),
    "largest": (lambda row: (row.amount, row.created_at, row.id), True),
}


async def list_expenses(
    session: AsyncSession,
    date_range: DateRange,
    *,
    category: Category | None,
    member: Member | None,
    search: str | None,
    min_amount: int | None,
    sort: SortOrder,
    limit: int,
    offset: int,
) -> ExpensePage:
    query = (
        select(
            Expense.id,
            Expense.created_at,
            Expense.amount,
            Expense.description,
            Category.name.label("category"),
            Member.display_name.label("member"),
        )
        .join(Category, Category.id == Expense.category_id)
        .join(Member, Member.id == Expense.member_id)
        .where(*_conditions(date_range, category, member))
    )
    if min_amount is not None:
        query = query.where(Expense.amount >= min_amount)
    rows = list((await session.execute(query)).all())

    needle = (search or "").strip().casefold()
    if needle:
        # In Python, not SQL: SQLite's LOWER() only folds ASCII letters.
        rows = [row for row in rows if row.description and needle in row.description.casefold()]

    key, reverse = _SORTS[sort]
    rows.sort(key=key, reverse=reverse)
    page = rows[offset : offset + limit]
    return ExpensePage(
        items=[
            ExpenseItem(
                id=row.id,
                datetime=to_kyiv(row.created_at),
                amount=row.amount,
                category=row.category,
                member=row.member,
                description=row.description,
            )
            for row in page
        ],
        total_count=len(rows),
        offset=offset,
        next_offset=offset + limit if offset + limit < len(rows) else None,
    )
```

- [ ] **Step 5: Запустити — зелені**

Run: `.venv/bin/python -m pytest tests/test_connector_list.py tests/test_connector_trend.py tests/test_connector_summary.py -q`
Expected: усі проходять.

- [ ] **Step 6: Повний набір і лінт**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

- [ ] **Step 7: Commit**

```bash
git add src/budget_bot/connector/schemas.py src/budget_bot/connector/analytics.py tests/test_connector_list.py
git commit -m "feat: page through expenses for the Claude connector"
```

---

### Task 6: MCP tools

**Files:**
- Modify: `tg-bot/pyproject.toml`
- Create: `tg-bot/src/budget_bot/connector/tools.py`
- Test: `tg-bot/tests/test_connector_tools.py`

**Interfaces:**
- Consumes: усе з `analytics` (Tasks 3–5), `inputs` (Task 2), `schemas`; `budget_bot.clock.utcnow`.
- Produces (`budget_bot.connector.tools`):
  - `SessionFactory = async_sessionmaker[AsyncSession]`
  - `build_mcp_server(session_factory: SessionFactory) -> MCPServer` з інструментами `get_budget_overview`, `summarize_spending`, `get_spending_trend`, `list_expenses`.
  - `INTERNAL_ERROR_TEXT`; рядок логу `MCP tool <name> by <label>: <ok|invalid_request|internal_error> in <ms> ms`, де `<label>` береться з `request.state.mcp_token_label` (гейт Task 7) або `-`.

- [ ] **Step 1: Додати залежність і встановити**

У `tg-bot/pyproject.toml` у `[project] dependencies` після `"pydantic-settings>=2.6",` додати:

```toml
    # Exact pin: pydantic must satisfy both aiogram (<2.14) and mcp (>=2.12).
    "mcp==2.2.0",
```

Run: `.venv/bin/pip install -e ".[dev]" && .venv/bin/pip check && .venv/bin/pip show mcp pydantic | grep -E "^(Name|Version)"`
Expected: `No broken requirements found.`; `mcp 2.2.0`; pydantic `2.12.x` або `2.13.x`.

- [ ] **Step 2: Написати падаючий тест**

`tg-bot/tests/test_connector_tools.py`:

```python
import logging

import pytest
from mcp import Client

from budget_bot.connector.tools import INTERNAL_ERROR_TEXT, build_mcp_server
from budget_bot.db import create_readonly_engine, create_session_factory

SEPTEMBER = {"start_date": "2026-09-01", "end_date": "2026-09-30"}


async def call(session_factory, name: str, arguments: dict | None = None):
    async with Client(build_mcp_server(session_factory)) as client:
        return await client.call_tool(name, arguments or {})


def text_of(result) -> str:
    return "\n".join(block.text for block in result.content)


async def test_every_tool_is_titled_and_read_only(readonly_session_factory):
    async with Client(build_mcp_server(readonly_session_factory)) as client:
        tools = (await client.list_tools()).tools

    assert {tool.name for tool in tools} == {
        "get_budget_overview",
        "summarize_spending",
        "get_spending_trend",
        "list_expenses",
    }
    for tool in tools:
        assert tool.title, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.open_world_hint is False, tool.name


async def test_results_arrive_as_structured_content(early_september, readonly_session_factory):
    result = await call(
        readonly_session_factory,
        "summarize_spending",
        {"start_date": "2026-09-14", "end_date": "2026-09-14", "category": "їжа"},
    )
    assert result.is_error is False
    assert result.structured_content == {
        "start_date": "2026-09-14",
        "end_date": "2026-09-14",
        "category": "Їжа",
        "member": None,
        "total": 1200,
        "expense_count": 1,
        "by_category": [{"name": "Їжа", "amount": 1200, "share_percent": 100.0, "count": 1}],
        "by_member": [{"name": "Оля", "amount": 1200, "count": 1}],
    }


@pytest.mark.parametrize(
    ("tool", "arguments", "hint"),
    [
        (
            "summarize_spending",
            {"start_date": "01.09.2026", "end_date": "2026-09-30"},
            "YYYY-MM-DD",
        ),
        (
            "summarize_spending",
            {"start_date": "2026-09-30", "end_date": "2026-09-01"},
            "is before start_date",
        ),
        ("summarize_spending", {**SEPTEMBER, "category": "Кава"}, "Known categories: Їжа"),
        ("get_spending_trend", {**SEPTEMBER, "member": "Петро"}, "Known members: Сергій, Оля"),
        (
            "get_spending_trend",
            {"start_date": "2020-01-01", "end_date": "2026-12-31", "granularity": "week"},
            'use granularity="month"',
        ),
        ("list_expenses", {**SEPTEMBER, "limit": 500}, "limit must be between 1 and 200"),
        ("list_expenses", {**SEPTEMBER, "offset": -1}, "offset must be 0 or greater"),
        ("list_expenses", {**SEPTEMBER, "min_amount": -5}, "min_amount must be 0 or greater"),
    ],
)
async def test_fixable_mistakes_come_back_as_errors_with_a_hint(
    readonly_session_factory, tool, arguments, hint
):
    result = await call(readonly_session_factory, tool, arguments)
    assert result.is_error is True
    assert hint in text_of(result)


async def test_unexpected_failure_hides_details_and_logs_the_traceback(tmp_path, caplog):
    # SQLite cannot open a missing file read-only: a real failure, not a mock.
    engine = create_readonly_engine(tmp_path / "missing.sqlite3")
    try:
        with caplog.at_level(logging.INFO):
            result = await call(create_session_factory(engine), "get_budget_overview")
    finally:
        await engine.dispose()

    assert result.is_error is True
    assert INTERNAL_ERROR_TEXT in text_of(result)
    assert "unable to open" not in text_of(result)
    failure = next(
        r for r in caplog.records if r.getMessage() == "MCP tool get_budget_overview failed"
    )
    assert failure.exc_info is not None
    assert "MCP tool get_budget_overview by -: internal_error in" in caplog.text


async def test_calls_are_logged_with_their_outcome_but_never_with_data(
    early_september, readonly_session_factory, caplog
):
    with caplog.at_level(logging.INFO):
        await call(readonly_session_factory, "list_expenses", {**SEPTEMBER, "search": "таксі"})
        await call(
            readonly_session_factory, "summarize_spending", {**SEPTEMBER, "category": "Кава"}
        )

    assert "MCP tool list_expenses by -: ok in" in caplog.text
    assert "MCP tool summarize_spending by -: invalid_request in" in caplog.text
    for data in ("таксі", "Таксі", "Кава", "Оля", "Транспорт"):
        assert data not in caplog.text
```

- [ ] **Step 3: Запустити — має впасти**

Run: `.venv/bin/python -m pytest tests/test_connector_tools.py -q`
Expected: `ModuleNotFoundError: No module named 'budget_bot.connector.tools'`.

- [ ] **Step 4: Реалізувати інструменти**

`tg-bot/src/budget_bot/connector/tools.py`:

```python
"""MCP tools of the Claude connector: registration, argument checks, call logging."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from budget_bot.clock import utcnow
from budget_bot.connector import analytics
from budget_bot.connector.inputs import (
    InvalidRequest,
    check_limit,
    check_not_negative,
    parse_date_range,
)
from budget_bot.connector.schemas import (
    BudgetOverview,
    ExpensePage,
    Granularity,
    SortOrder,
    SpendingSummary,
    SpendingTrend,
    SplitBy,
)

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
INTERNAL_ERROR_TEXT = "Internal error while reading budget data; try again later."
SDK_SERVER_LOGGER = "mcp.server.mcpserver.server"

SessionFactory = async_sessionmaker[AsyncSession]

StartDate = Annotated[
    str, Field(description="First day of the range, YYYY-MM-DD, a Kyiv calendar day, inclusive")
]
EndDate = Annotated[
    str, Field(description="Last day of the range, YYYY-MM-DD, a Kyiv calendar day, inclusive")
]
CategoryName = Annotated[
    str | None, Field(description="Only this category, matched by name ignoring case")
]
MemberName = Annotated[
    str | None,
    Field(description="Only expenses recorded by this member, matched by name ignoring case"),
]

OVERVIEW_DESCRIPTION = (
    "Returns what the family budget data covers: today's date in Kyiv, the currency (UAH), "
    "household members, expense categories, the dates of the first and last recorded expense "
    "and the number of expenses. Expense dates are when an expense was recorded in the "
    "Telegram bot."
)
SUMMARY_DESCRIPTION = (
    "Returns total spending in whole UAH for an inclusive range of Kyiv calendar days: the "
    "number of expenses, a breakdown by category (amount, share of the total in percent, "
    "count) and a breakdown by member (amount, count). Can be narrowed to one category "
    "and/or one member."
)
TREND_DESCRIPTION = (
    "Returns spending in whole UAH per calendar week (Monday to Sunday) or per calendar "
    "month, in Kyiv time, across an inclusive date range, optionally split by category or "
    "by member. Weeks or months cut short by the range are marked partial. At most 60 "
    "buckets per call."
)
LIST_DESCRIPTION = (
    "Returns individual expenses for an inclusive range of Kyiv calendar days, one page at a "
    "time: id (the number the bot shows as «Витрата #N»), date and time in Kyiv, amount in "
    "whole UAH, category, the member who recorded it and the description. Filters: category, "
    "member, a case-insensitive text in the description, a minimum amount. Sorted newest "
    "first, oldest first or largest first."
)


def build_mcp_server(session_factory: SessionFactory) -> MCPServer:
    # The SDK logs the text of every ToolError at INFO, and ours name categories
    # and members. Its warnings and errors still get through.
    logging.getLogger(SDK_SERVER_LOGGER).setLevel(logging.WARNING)
    server = MCPServer(name="family-budget")

    @server.tool(
        name="get_budget_overview",
        title="Огляд бюджету",
        description=OVERVIEW_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def get_budget_overview(ctx: Context) -> BudgetOverview:
        async def work(session: AsyncSession) -> BudgetOverview:
            return await analytics.budget_overview(session, now_utc=utcnow())

        return await _run("get_budget_overview", ctx, session_factory, work)

    @server.tool(
        name="summarize_spending",
        title="Підсумок витрат",
        description=SUMMARY_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def summarize_spending(
        ctx: Context,
        start_date: StartDate,
        end_date: EndDate,
        category: CategoryName = None,
        member: MemberName = None,
    ) -> SpendingSummary:
        async def work(session: AsyncSession) -> SpendingSummary:
            date_range = parse_date_range(start_date, end_date)
            return await analytics.summarize_spending(
                session,
                date_range,
                category=await analytics.find_category(session, category),
                member=await analytics.find_member(session, member),
            )

        return await _run("summarize_spending", ctx, session_factory, work)

    @server.tool(
        name="get_spending_trend",
        title="Динаміка витрат",
        description=TREND_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def get_spending_trend(
        ctx: Context,
        start_date: StartDate,
        end_date: EndDate,
        granularity: Annotated[
            Granularity,
            Field(description="week: Monday to Sunday; month: calendar month; both in Kyiv time"),
        ] = "month",
        split_by: Annotated[
            SplitBy, Field(description="Add a per-bucket breakdown by category or by member")
        ] = "none",
        category: CategoryName = None,
        member: MemberName = None,
    ) -> SpendingTrend:
        async def work(session: AsyncSession) -> SpendingTrend:
            date_range = parse_date_range(start_date, end_date)
            return await analytics.spending_trend(
                session,
                date_range,
                granularity=granularity,
                split_by=split_by,
                category=await analytics.find_category(session, category),
                member=await analytics.find_member(session, member),
            )

        return await _run("get_spending_trend", ctx, session_factory, work)

    @server.tool(
        name="list_expenses",
        title="Список витрат",
        description=LIST_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def list_expenses(
        ctx: Context,
        start_date: StartDate,
        end_date: EndDate,
        category: CategoryName = None,
        member: MemberName = None,
        search: Annotated[
            str | None, Field(description="Text to look for in descriptions, ignoring case")
        ] = None,
        min_amount: Annotated[
            int | None, Field(description="Only expenses of at least this many UAH")
        ] = None,
        sort: Annotated[
            SortOrder, Field(description="newest first, oldest first or largest amount first")
        ] = "newest",
        limit: Annotated[int, Field(description="Page size, 1 to 200")] = 50,
        offset: Annotated[
            int, Field(description="Expenses to skip: next_offset from the previous page")
        ] = 0,
    ) -> ExpensePage:
        async def work(session: AsyncSession) -> ExpensePage:
            date_range = parse_date_range(start_date, end_date)
            check_limit(limit)
            check_not_negative("offset", offset)
            check_not_negative("min_amount", min_amount)
            return await analytics.list_expenses(
                session,
                date_range,
                category=await analytics.find_category(session, category),
                member=await analytics.find_member(session, member),
                search=search,
                min_amount=min_amount,
                sort=sort,
                limit=limit,
                offset=offset,
            )

        return await _run("list_expenses", ctx, session_factory, work)

    return server


async def _run[T](
    name: str,
    ctx: Context,
    session_factory: SessionFactory,
    work: Callable[[AsyncSession], Awaitable[T]],
) -> T:
    """Run one tool call in its own read session and log how it ended.

    InvalidRequest becomes a ToolError the model can act on. Anything else is
    logged with its traceback and reported without internals. The log line
    never carries arguments or results: they are the family's financial data.
    """
    started = time.perf_counter()
    outcome = "internal_error"
    try:
        async with session_factory() as session:
            result = await work(session)
        outcome = "ok"
        return result
    except InvalidRequest as exc:
        outcome = "invalid_request"
        raise ToolError(str(exc)) from None
    except Exception:
        logger.exception("MCP tool %s failed", name)
        raise ToolError(INTERNAL_ERROR_TEXT) from None
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "MCP tool %s by %s: %s in %.0f ms", name, _token_label(ctx), outcome, elapsed_ms
        )


def _token_label(ctx: Context) -> str:
    """Label of the bearer token that authenticated this HTTP call (set by BearerGate)."""
    request = ctx.request_context.request
    if request is None:  # in-process calls, e.g. tests
        return "-"
    return getattr(request.state, "mcp_token_label", "-")
```

- [ ] **Step 5: Запустити — зелені**

Run: `.venv/bin/python -m pytest tests/test_connector_tools.py -q`
Expected: усі проходять. Якщо падає лише `test_calls_are_logged_with_their_outcome_but_never_with_data` із рядком `Tool 'summarize_spending' failed: …` у лозі — пропущено рядок `logging.getLogger(SDK_SERVER_LOGGER).setLevel(logging.WARNING)`.

- [ ] **Step 6: Повний набір і лінт**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/budget_bot/connector/tools.py tests/test_connector_tools.py
git commit -m "feat: expose budget analytics as read-only MCP tools"
```

---

### Task 7: Bearer-token gate

**Files:**
- Create: `tg-bot/src/budget_bot/connector/auth.py`
- Test: `tg-bot/tests/test_connector_auth.py`

**Interfaces:**
- Consumes: Starlette (прийшов разом із mcp у Task 6).
- Produces (`budget_bot.connector.auth`):
  - `class AccessTokenError(ValueError)` — текст ніколи не містить токена.
  - `parse_access_tokens(raw: str) -> dict[str, str]` — `{token: label}`.
  - `class BearerGate: __init__(self, app: ASGIApp, tokens: Mapping[str, str])` — ASGI-middleware: `lifespan` пропускає, HTTP без валідного токена → `401`; для валідного кладе `scope["state"]["mcp_token_label"]`; відмову логує WARNING `MCP access denied: <missing|invalid> bearer token from <client>`.

- [ ] **Step 1: Написати падаючий тест**

`tg-bot/tests/test_connector_auth.py`:

```python
import logging

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from budget_bot.connector.auth import AccessTokenError, BearerGate, parse_access_tokens

SERHII_TOKEN = "s" * 40
YULIA_TOKEN = "y" * 40


def test_parses_labelled_tokens_ignoring_spaces_and_a_trailing_comma():
    raw = f" serhii:{SERHII_TOKEN} , yulia:{YULIA_TOKEN},"
    assert parse_access_tokens(raw) == {SERHII_TOKEN: "serhii", YULIA_TOKEN: "yulia"}


@pytest.mark.parametrize(
    ("raw", "hint"),
    [
        ("", "no label:token entries found"),
        (SERHII_TOKEN, "entry 1: expected label:token"),
        (f":{SERHII_TOKEN}", "entry 1: expected label:token"),
        (f"Serhii:{SERHII_TOKEN}", "entry 1: expected label:token"),
        ("serhii:" + "s" * 31, "the token for 'serhii' is shorter than 32 characters"),
        (f"serhii:{SERHII_TOKEN},serhii:{YULIA_TOKEN}", "label 'serhii' is used twice"),
        (f"serhii:{SERHII_TOKEN},yulia:{SERHII_TOKEN}", "'serhii' and 'yulia' share a token"),
    ],
)
def test_malformed_configuration_is_rejected_without_echoing_tokens(raw, hint):
    with pytest.raises(AccessTokenError) as excinfo:
        parse_access_tokens(raw)
    message = str(excinfo.value)
    assert hint in message
    assert "sss" not in message and "yyy" not in message


def gated_app() -> BearerGate:
    async def whoami(request: Request) -> PlainTextResponse:
        return PlainTextResponse(request.state.mcp_token_label)

    app = Starlette(routes=[Route("/mcp", whoami, methods=["POST"])])
    return BearerGate(app, {SERHII_TOKEN: "serhii", YULIA_TOKEN: "yulia"})


@pytest.mark.parametrize(
    ("authorization", "label"),
    [
        (f"Bearer {SERHII_TOKEN}", "serhii"),
        (f"Bearer {YULIA_TOKEN}", "yulia"),
        (f"bearer {SERHII_TOKEN}", "serhii"),
    ],
)
def test_valid_token_reaches_the_app_with_its_label(authorization, label):
    with TestClient(gated_app()) as client:
        response = client.post("/mcp", headers={"Authorization": authorization})
    assert response.status_code == 200
    assert response.text == label


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": f"Bearer {'x' * 40}"},
        {"Authorization": f"Basic {SERHII_TOKEN}"},
        {"Authorization": SERHII_TOKEN},
        {"Authorization": "Bearer"},
    ],
)
def test_request_without_a_valid_bearer_token_gets_a_plain_401(headers):
    with TestClient(gated_app()) as client:
        response = client.post("/mcp", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.text == "Unauthorized"


def test_denials_are_logged_with_reason_and_client_but_never_the_token(caplog):
    with caplog.at_level(logging.WARNING), TestClient(gated_app()) as client:
        client.post("/mcp")
        client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {'x' * 40}",
                "X-Forwarded-For": "203.0.113.7, 10.0.0.1",
            },
        )
    assert [r.getMessage() for r in caplog.records if r.name == "budget_bot.connector.auth"] == [
        "MCP access denied: missing bearer token from testclient",
        "MCP access denied: invalid bearer token from 203.0.113.7",
    ]
    assert "xxx" not in caplog.text
```

- [ ] **Step 2: Запустити — має впасти**

Run: `.venv/bin/python -m pytest tests/test_connector_auth.py -q`
Expected: `ModuleNotFoundError: No module named 'budget_bot.connector.auth'`.

- [ ] **Step 3: Реалізувати гейт**

`tg-bot/src/budget_bot/connector/auth.py`:

```python
"""Bearer-token access to the Claude connector.

MCP_ACCESS_TOKENS holds one ``label:token`` pair per person, so access can be
revoked for one person without touching the other, and logs can say who
called without ever containing a token.
"""

import hmac
import logging
import re
from collections.abc import Mapping

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

MIN_TOKEN_LENGTH = 32
_LABEL = re.compile(r"[a-z0-9_-]{1,32}")


class AccessTokenError(ValueError):
    """MCP_ACCESS_TOKENS is malformed. Messages never include a token."""


def parse_access_tokens(raw: str) -> dict[str, str]:
    """Parse ``label:token,label:token`` into a {token: label} mapping."""
    tokens: dict[str, str] = {}
    for position, chunk in enumerate(raw.split(","), start=1):
        if not chunk.strip():
            continue
        label, separator, token = (part.strip() for part in chunk.partition(":"))
        if not separator or not _LABEL.fullmatch(label):
            raise AccessTokenError(
                f"entry {position}: expected label:token, the label being 1-32 characters "
                "of a-z, 0-9, _ or -"
            )
        if len(token) < MIN_TOKEN_LENGTH:
            raise AccessTokenError(
                f"the token for {label!r} is shorter than {MIN_TOKEN_LENGTH} characters"
            )
        if label in tokens.values():
            raise AccessTokenError(f"label {label!r} is used twice")
        if token in tokens:
            raise AccessTokenError(f"labels {tokens[token]!r} and {label!r} share a token")
        tokens[token] = label
    if not tokens:
        raise AccessTokenError("no label:token entries found")
    return tokens


class BearerGate:
    """ASGI middleware: an HTTP request without a valid bearer token never reaches MCP.

    A rejection is a plain 401 with ``WWW-Authenticate: Bearer`` and nothing
    else — in particular no OAuth ``resource_metadata``, which would send
    Claude looking for an authorization server this connector does not have.
    The label of an accepted token is put into the request state as
    ``mcp_token_label`` for logging.
    """

    def __init__(self, app: ASGIApp, tokens: Mapping[str, str]) -> None:
        self.app = app
        self._tokens = [(token.encode(), label) for token, label in tokens.items()]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return

        presented = _bearer_token(scope)
        label = self._label_for(presented) if presented is not None else None
        if label is None:
            reason = "missing" if presented is None else "invalid"
            logger.warning(
                "MCP access denied: %s bearer token from %s", reason, _client_address(scope)
            )
            await _unauthorized(send)
            return

        scope.setdefault("state", {})["mcp_token_label"] = label
        await self.app(scope, receive, send)

    def _label_for(self, presented: str) -> str | None:
        candidate = presented.encode()
        found = None
        # Compare against every token without stopping early, in constant time.
        for token, label in self._tokens:
            if hmac.compare_digest(candidate, token):
                found = label
        return found


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return value.decode("latin-1")
    return None


def _bearer_token(scope: Scope) -> str | None:
    """The presented credentials; "" when the header is not a usable bearer token."""
    header = _header(scope, b"authorization")
    if header is None:
        return None
    scheme, _, credentials = header.strip().partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return credentials.strip()


def _client_address(scope: Scope) -> str:
    forwarded = _header(scope, b"x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _unauthorized(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Unauthorized"})
```

- [ ] **Step 4: Запустити — зелені**

Run: `.venv/bin/python -m pytest tests/test_connector_auth.py -q`
Expected: усі проходять.

- [ ] **Step 5: Повний набір і лінт**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

- [ ] **Step 6: Commit**

```bash
git add src/budget_bot/connector/auth.py tests/test_connector_auth.py
git commit -m "feat: guard the Claude connector with per-person bearer tokens"
```

---

### Task 8: Connector configuration, HTTP app and server

**Files:**
- Modify: `tg-bot/pyproject.toml`
- Modify: `tg-bot/src/budget_bot/config.py`
- Create: `tg-bot/src/budget_bot/connector/server.py`
- Test: `tg-bot/tests/test_config.py`, `tg-bot/tests/test_connector_server.py`

**Interfaces:**
- Consumes: `build_mcp_server`, `SessionFactory` (Task 6); `BearerGate`, `parse_access_tokens`, `AccessTokenError` (Task 7); фікстура `readonly_session_factory` (Task 3).
- Produces:
  - `Settings.mcp_access_tokens_raw: str | None` (`MCP_ACCESS_TOKENS`), `Settings.mcp_public_host: str | None` (`MCP_PUBLIC_HOST`), `Settings.port: int = 8080` (`PORT`).
  - `budget_bot.connector.server`:
    - `@dataclass(frozen=True) class ConnectorConfig: tokens: dict[str, str]; public_host: str; port: int`
    - `connector_config(settings: Settings) -> ConnectorConfig | None` — `None` з причиною в лозі, коли конектор має лишатися вимкненим.
    - `build_connector_app(session_factory: SessionFactory, tokens: Mapping[str, str], public_host: str) -> ASGIApp`
    - `class ConnectorServer(uvicorn.Server)` — no-op `capture_signals()`.
    - `build_connector_server(app: ASGIApp, port: int, host: str = "0.0.0.0") -> ConnectorServer`
    - `async def serve_connector(server: uvicorn.Server) -> None` — ловить `Exception` і `SystemExit`; логує `Claude connector stopped; the bot keeps running` (збій) або `Claude connector stopped` (штатно).

- [ ] **Step 1: Зафіксувати uvicorn**

У `tg-bot/pyproject.toml` після рядка `"mcp==2.2.0",` додати:

```toml
    # ConnectorServer overrides uvicorn's capture_signals(); upgrade only with
    # tests/test_connector_lifecycle.py passing.
    "uvicorn>=0.53,<0.54",
```

Run: `.venv/bin/pip install -e ".[dev]" && .venv/bin/pip check`
Expected: `No broken requirements found.`

- [ ] **Step 2: Написати падаючі тести конфігу**

`tg-bot/tests/test_config.py` (повністю):

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


def test_reads_connector_settings_from_their_env_names():
    settings = make_settings(
        MCP_ACCESS_TOKENS="serhii:abc", MCP_PUBLIC_HOST="budget.example", PORT="9000"
    )
    assert settings.mcp_access_tokens_raw == "serhii:abc"
    assert settings.mcp_public_host == "budget.example"
    assert settings.port == 9000


def test_connector_settings_are_optional():
    settings = make_settings()
    assert (settings.mcp_access_tokens_raw, settings.mcp_public_host, settings.port) == (
        None,
        None,
        8080,
    )
```

- [ ] **Step 3: Написати падаючі тести сервера**

`tg-bot/tests/test_connector_server.py`:

```python
import logging
import socket

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from budget_bot.config import Settings
from budget_bot.connector.server import (
    ConnectorConfig,
    build_connector_app,
    build_connector_server,
    connector_config,
    serve_connector,
)

TOKEN = "s" * 40
PROTOCOL_VERSION = "2025-11-25"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    },
}


def make_settings(**env) -> Settings:
    return Settings(_env_file=None, TELEGRAM_BOT_TOKEN="123:ABC", ALLOWED_TELEGRAM_IDS="111", **env)


@pytest.mark.parametrize("env", [{}, {"MCP_ACCESS_TOKENS": "   "}])
def test_connector_stays_off_without_tokens(env, caplog):
    with caplog.at_level(logging.INFO):
        assert connector_config(make_settings(**env)) is None
    assert "Claude connector disabled: MCP_ACCESS_TOKENS is not set" in caplog.text


def test_valid_configuration_enables_the_connector():
    settings = make_settings(
        MCP_ACCESS_TOKENS=f"serhii:{TOKEN}", MCP_PUBLIC_HOST="budget.up.railway.app", PORT="9000"
    )
    assert connector_config(settings) == ConnectorConfig(
        tokens={TOKEN: "serhii"}, public_host="budget.up.railway.app", port=9000
    )


def test_malformed_tokens_switch_the_connector_off_loudly(caplog):
    settings = make_settings(MCP_ACCESS_TOKENS="serhii:" + "q" * 10, MCP_PUBLIC_HOST="budget.test")
    with caplog.at_level(logging.INFO):
        assert connector_config(settings) is None
    assert any(
        r.levelno == logging.ERROR
        and "Claude connector disabled: MCP_ACCESS_TOKENS is invalid" in r.getMessage()
        for r in caplog.records
    )
    assert "qqq" not in caplog.text


def test_tokens_without_a_public_host_switch_the_connector_off(caplog):
    with caplog.at_level(logging.ERROR):
        assert connector_config(make_settings(MCP_ACCESS_TOKENS=f"serhii:{TOKEN}")) is None
    assert "MCP_PUBLIC_HOST must be set" in caplog.text


@pytest.fixture
def connector_app(readonly_session_factory):
    # A fresh app per test: the SDK's session manager runs only once per app.
    return build_connector_app(readonly_session_factory, {TOKEN: "serhii"}, "testserver")


async def test_initialize_is_served_on_mcp_without_a_redirect(connector_app):
    with TestClient(connector_app) as client:
        response = client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS, follow_redirects=False)
    assert response.status_code == 200
    assert response.json()["result"]["protocolVersion"] == PROTOCOL_VERSION


async def test_unauthenticated_request_is_refused_without_oauth_metadata(connector_app):
    headers = {k: v for k, v in MCP_HEADERS.items() if k != "Authorization"}
    with TestClient(connector_app) as client:
        response = client.post("/mcp", json=INITIALIZE, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_unexpected_host_is_refused(connector_app):
    with TestClient(connector_app) as client:
        response = client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Host": "evil.example"}
        )
    assert response.status_code == 421


async def test_requests_from_claude_ai_are_accepted(connector_app):
    with TestClient(connector_app) as client:
        response = client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Origin": "https://claude.ai"}
        )
    assert response.status_code == 200


async def test_tool_call_over_http_logs_the_token_label_but_not_the_token(connector_app, caplog):
    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "get_budget_overview", "arguments": {}},
    }
    with caplog.at_level(logging.INFO), TestClient(connector_app) as client:
        response = client.post(
            "/mcp", json=call, headers={**MCP_HEADERS, "MCP-Protocol-Version": PROTOCOL_VERSION}
        )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is False
    assert "MCP tool get_budget_overview by serhii: ok in" in caplog.text
    assert TOKEN not in caplog.text


async def test_connector_that_cannot_bind_its_port_does_not_raise(caplog):
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        server = build_connector_server(
            Starlette(), port=blocker.getsockname()[1], host="127.0.0.1"
        )
        with caplog.at_level(logging.ERROR):
            await serve_connector(server)  # a SystemExit escaping here would fail the test run
    assert "Claude connector stopped; the bot keeps running" in caplog.text
```

- [ ] **Step 4: Запустити — мають впасти**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_connector_server.py -q`
Expected: `AttributeError: 'Settings' object has no attribute 'mcp_access_tokens_raw'` у двох нових тестах конфігу і `ModuleNotFoundError: No module named 'budget_bot.connector.server'` при зборі тестів сервера.

- [ ] **Step 5: Додати змінні в `Settings`**

`tg-bot/src/budget_bot/config.py` (повністю):

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
    # Claude connector. Kept raw and optional on purpose: a mistake here must
    # only switch the connector off (see connector.server.connector_config),
    # never stop the bot from starting.
    mcp_access_tokens_raw: str | None = Field(default=None, alias="MCP_ACCESS_TOKENS")
    mcp_public_host: str | None = Field(default=None, alias="MCP_PUBLIC_HOST")
    port: int = Field(default=8080, alias="PORT")

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

- [ ] **Step 6: Реалізувати сервер**

`tg-bot/src/budget_bot/connector/server.py`:

```python
"""HTTP side of the Claude connector: configuration, ASGI app and uvicorn server.

The connector runs inside the bot's process (the SQLite volume can be mounted
into only one service), so everything here fails on its own: a bad
configuration or a crashed server is logged, and the bot keeps polling.
"""

import contextlib
import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp

from budget_bot.config import Settings
from budget_bot.connector.auth import AccessTokenError, BearerGate, parse_access_tokens
from budget_bot.connector.tools import SessionFactory, build_mcp_server

logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"
CLAUDE_ORIGIN = "https://claude.ai"
SHUTDOWN_GRACE_SECONDS = 5


@dataclass(frozen=True)
class ConnectorConfig:
    tokens: dict[str, str]  # token -> label
    public_host: str
    port: int


def connector_config(settings: Settings) -> ConnectorConfig | None:
    """The connector's settings, or None (with the reason logged) when it must stay off."""
    raw_tokens = (settings.mcp_access_tokens_raw or "").strip()
    if not raw_tokens:
        logger.info("Claude connector disabled: MCP_ACCESS_TOKENS is not set")
        return None
    try:
        tokens = parse_access_tokens(raw_tokens)
    except AccessTokenError as exc:
        logger.error("Claude connector disabled: MCP_ACCESS_TOKENS is invalid (%s)", exc)
        return None
    public_host = (settings.mcp_public_host or "").strip()
    if not public_host:
        logger.error(
            "Claude connector disabled: MCP_PUBLIC_HOST must be set when MCP_ACCESS_TOKENS is"
        )
        return None
    logger.info(
        "Claude connector enabled on port %d for %s",
        settings.port,
        ", ".join(sorted(tokens.values())),
    )
    return ConnectorConfig(tokens=tokens, public_host=public_host, port=settings.port)


def build_connector_app(
    session_factory: SessionFactory, tokens: Mapping[str, str], public_host: str
) -> ASGIApp:
    """The MCP endpoint behind the bearer-token gate.

    The gate wraps the SDK app directly rather than through a Mount: the SDK
    serves /mcp as an exact route, while a Mount would redirect /mcp to
    /mcp/ — and a redirect drops the Authorization header.
    """
    mcp_app = build_mcp_server(session_factory).streamable_http_app(
        streamable_http_path=MCP_PATH,
        # Plain request/response: no in-memory sessions to lose on a redeploy
        # and no long-lived streams for Railway's edge to cut off.
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_host],
            allowed_origins=[CLAUDE_ORIGIN],
        ),
    )
    return BearerGate(mcp_app, tokens)


class ConnectorServer(uvicorn.Server):
    """uvicorn server that leaves SIGINT/SIGTERM to aiogram.

    Stock uvicorn installs its handlers with signal.signal() when it starts
    and restores the ones it found when it stops. The connector starts before
    aiogram registers its handlers, so after the connector stopped SIGTERM
    would be back to its default action, and a repeated SIGTERM during
    cleanup would kill the process. The bot stops the connector explicitly.
    """

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def build_connector_server(app: ASGIApp, port: int, host: str = "0.0.0.0") -> ConnectorServer:
    return ConnectorServer(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            lifespan="on",
            log_config=None,  # keep the bot's logging setup
            access_log=False,
            server_header=False,
            timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS,
        )
    )


async def serve_connector(server: uvicorn.Server) -> None:
    """Serve until told to exit; never let the connector's failure escape.

    uvicorn calls sys.exit(1) when it cannot bind its port or its lifespan
    fails. A SystemExit raised inside an asyncio task stops the whole event
    loop — and the bot with it — so it is caught here with everything else.
    """
    try:
        await server.serve()
    except (Exception, SystemExit):
        logger.exception("Claude connector stopped; the bot keeps running")
        return
    logger.info("Claude connector stopped")
```

- [ ] **Step 7: Запустити — зелені**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_connector_server.py -q`
Expected: усі проходять.

- [ ] **Step 8: Повний набір і лінт**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml src/budget_bot/config.py src/budget_bot/connector/server.py tests/test_config.py tests/test_connector_server.py
git commit -m "feat: serve the Claude connector over HTTP with isolated failures"
```

---

### Task 9: Run the connector alongside polling

**Files:**
- Modify: `tg-bot/src/budget_bot/__main__.py`
- Create: `tg-bot/tests/connector_lifecycle_app.py`
- Test: `tg-bot/tests/test_connector_lifecycle.py`

**Interfaces:**
- Consumes: `connector_config`, `build_connector_app`, `build_connector_server`, `serve_connector` (Task 8); `create_readonly_engine` (Task 1).
- Produces: `budget_bot.__main__.run_bot(dispatcher: Dispatcher, bot: Bot, connector: uvicorn.Server | None) -> None` — стартує конектор, реєструє команди бота, опитує Telegram до SIGINT/SIGTERM, потім зупиняє конектор і чекає на нього. `main()` вмикає конектор, лише коли `connector_config` повернув конфіг, і закриває read-only engine.

- [ ] **Step 1: Написати допоміжний застосунок**

`tg-bot/tests/connector_lifecycle_app.py` (pytest його не збирає: ім'я не починається з `test_`):

```python
"""The bot's run loop with the real aiogram Dispatcher and a real connector server.

Only Telegram is faked. Started as a subprocess by test_connector_lifecycle.py:
``python connector_lifecycle_app.py <port>``.
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, GetUpdates, SetMyCommands
from aiogram.types import User
from starlette.applications import Starlette

from budget_bot.__main__ import run_bot
from budget_bot.connector.server import build_connector_server


class FakeTelegramSession(BaseSession):
    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="Test", username="test_bot")
        if isinstance(method, GetUpdates):
            await asyncio.sleep(0.1)
            return []
        if isinstance(method, SetMyCommands):
            # Like the real network call, this lets the connector start (and take
            # over signal handling, were it stock uvicorn) before aiogram
            # registers its own handlers.
            await asyncio.sleep(0.3)
            return True
        raise AssertionError(f"unexpected Telegram call: {type(method).__name__}")

    async def stream_content(self, *args, **kwargs):
        raise AssertionError("unexpected Telegram download")
        yield b""  # makes this an async generator, as the interface requires


async def main(port: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s", stream=sys.stdout)
    bot = Bot(token="42:TEST", session=FakeTelegramSession())
    connector = build_connector_server(Starlette(), port=port, host="127.0.0.1")
    try:
        await run_bot(Dispatcher(), bot, connector)
    finally:
        print("CLEANUP started", flush=True)
        await asyncio.sleep(1.0)  # stands in for closing the bot session and the engines
        print("CLEANUP finished", flush=True)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
```

- [ ] **Step 2: Написати падаючий тест**

`tg-bot/tests/test_connector_lifecycle.py`:

```python
"""Process-level shutdown behaviour of the bot with the Claude connector running."""

import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

APP = Path(__file__).with_name("connector_lifecycle_app.py")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class BotProcess:
    """connector_lifecycle_app.py in a subprocess, its output collected line by line."""

    def __init__(self) -> None:
        self.port = free_port()
        self.popen = subprocess.Popen(
            [sys.executable, "-u", str(APP), str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.lines: list[str] = []
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        for line in self.popen.stdout:
            self.lines.append(line.rstrip("\n"))

    def wait_for(self, fragment: str, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(fragment in line for line in self.lines):
                return
            if self.popen.poll() is not None:
                break
            time.sleep(0.05)
        raise AssertionError(f"{fragment!r} never appeared in:\n" + "\n".join(self.lines))

    def wait_until_serving(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        raise AssertionError("the connector never started listening")

    def line_index(self, fragment: str) -> int:
        return next(i for i, line in enumerate(self.lines) if fragment in line)

    def finish(self, timeout: float = 20.0) -> int:
        try:
            return self.popen.wait(timeout=timeout)
        finally:
            if self.popen.poll() is None:
                self.popen.kill()
            self._reader.join(timeout=2)


def start_bot() -> BotProcess:
    process = BotProcess()
    process.wait_for("Run polling for bot")
    process.wait_until_serving()
    return process


def test_sigterm_stops_polling_then_the_connector_then_cleans_up():
    process = start_bot()

    process.popen.send_signal(signal.SIGTERM)

    assert process.finish() == 0, "\n".join(process.lines)
    polling_stopped = process.line_index("Polling stopped")
    connector_stopped = process.line_index("Claude connector stopped")
    cleanup_finished = process.line_index("CLEANUP finished")
    assert polling_stopped < connector_stopped < cleanup_finished


def test_repeated_sigterm_during_cleanup_does_not_kill_the_process():
    process = start_bot()

    process.popen.send_signal(signal.SIGTERM)
    process.wait_for("CLEANUP started")
    process.popen.send_signal(signal.SIGTERM)

    assert process.finish() == 0, "\n".join(process.lines)
    assert any("CLEANUP finished" in line for line in process.lines)
```

- [ ] **Step 3: Запустити — має впасти**

Run: `.venv/bin/python -m pytest tests/test_connector_lifecycle.py -q`
Expected: обидва тести падають з `AssertionError: 'Run polling for bot' never appeared in:` і виводом підпроцесу, що містить `ImportError: cannot import name 'run_bot' from 'budget_bot.__main__'`.

- [ ] **Step 4: Запустити конектор поруч із polling**

`tg-bot/src/budget_bot/__main__.py` (повністю):

```python
"""Composition root: wires config, database, middlewares, handlers and the Claude connector."""

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, Update

from budget_bot.bot.handlers import build_router
from budget_bot.bot.middlewares import AccessMiddleware, DbSessionMiddleware
from budget_bot.config import Settings
from budget_bot.connector.server import (
    build_connector_app,
    build_connector_server,
    connector_config,
    serve_connector,
)
from budget_bot.db import create_engine, create_readonly_engine, create_session_factory

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="add", description="Додати витрату"),
    BotCommand(command="list", description="Останні витрати"),
    BotCommand(command="filter", description="Фільтр витрат"),
    BotCommand(command="report", description="Звіт за період"),
    BotCommand(command="categories", description="Категорії"),
    BotCommand(command="cancel", description="Перервати діалог"),
]

APOLOGY_TEXT = "⚠️ Виникла помилка. Спробуйте ще раз або /cancel."


def _chat_id(update: Update) -> int | None:
    if update.message is not None:
        return update.message.chat.id
    if update.callback_query is not None and update.callback_query.message is not None:
        return update.callback_query.message.chat.id
    return None


async def handle_error(event: ErrorEvent, bot: Bot) -> None:
    """Last-resort catch for exceptions no router or middleware handled.

    Registered on ``dispatcher.errors`` so an unhandled exception no longer
    just logs a traceback and leaves the user without a reply. Must never
    itself raise — that would propagate out of aiogram's ErrorsMiddleware
    and abort update processing.
    """
    logger.exception(
        "Unhandled error while processing update %s",
        event.update.update_id,
        exc_info=event.exception,
    )
    chat_id = _chat_id(event.update)
    if chat_id is None:
        return
    try:
        await bot.send_message(chat_id, APOLOGY_TEXT)
    except Exception:  # noqa: BLE001 - notifying about the error must not itself raise
        logger.exception("Failed to notify chat %s about an error", chat_id)


async def run_bot(dispatcher: Dispatcher, bot: Bot, connector: uvicorn.Server | None) -> None:
    """Poll Telegram until SIGINT/SIGTERM, running the Claude connector alongside.

    aiogram owns the signals. The connector starts first and is stopped only
    after polling has ended; its own failure never ends polling (see
    serve_connector).
    """
    connector_task = (
        asyncio.create_task(serve_connector(connector)) if connector is not None else None
    )
    try:
        await bot.set_my_commands(BOT_COMMANDS)
        await dispatcher.start_polling(bot)
    finally:
        if connector is not None and connector_task is not None:
            connector.should_exit = True
            await connector_task


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
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
    dispatcher.errors.register(handle_error)

    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    access = AccessMiddleware(settings.allowed_telegram_ids, settings.household_name)
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)

    dispatcher.include_router(build_router())

    readonly_engine = None
    connector = None
    config = connector_config(settings)
    if config is not None:
        readonly_engine = create_readonly_engine(settings.database_path)
        app = build_connector_app(
            create_session_factory(readonly_engine), config.tokens, config.public_host
        )
        connector = build_connector_server(app, config.port)

    try:
        await run_bot(dispatcher, bot, connector)
    finally:
        await bot.session.close()
        if readonly_engine is not None:
            await readonly_engine.dispose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Запустити — зелені**

Run: `.venv/bin/python -m pytest tests/test_connector_lifecycle.py -q`
Expected: 2 passed (≈5 с).

- [ ] **Step 6: Повний набір і лінт**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`
Expected: усі тести проходять (наявні `test_main.py` теж — `handle_error` не змінювався).

- [ ] **Step 7: Commit**

```bash
git add src/budget_bot/__main__.py tests/connector_lifecycle_app.py tests/test_connector_lifecycle.py
git commit -m "feat: run the Claude connector alongside the bot"
```

---

### Task 10: Documentation and local run

**Files:**
- Modify: `tg-bot/README.md`
- Modify: `tg-bot/.env.example`
- Modify: `tg-bot/docker-compose.yml`
- Modify: `CLAUDE.md` (корінь репозиторію)

**Interfaces:**
- Consumes: назви змінних і рядків логу з Tasks 6–9.
- Produces: інструкцію ввімкнення, підключення й ротації для людей.

- [ ] **Step 1: README — змінні в покроковій інструкції Railway**

У `tg-bot/README.md`, розділ «Railway: покроково», крок 4, після рядка `   - `RECENT_EXPENSES_LIMIT` (опційно)` додати:

```markdown
   - `MCP_ACCESS_TOKENS`, `MCP_PUBLIC_HOST` (опційно) — Claude-конектор, див. «Claude-конектор»
```

- [ ] **Step 2: README — розділ про конектор**

У `tg-bot/README.md` вставити перед заголовком другого рівня `## Конфіг` — тим, під яким таблиця змінних (не `### Конфігурація як код`):

````markdown
## Claude-конектор

Бот може віддавати витрати Claude на читання: у тому ж процесі працює MCP-сервер
на `/mcp`. Claude (claude.ai, Desktop, мобільний застосунок, Claude Code) бачить
чотири інструменти — огляд бюджету, підсумок за період, динаміку по тижнях чи
місяцях і список записів. Змінювати дані конектор не може: база відкривається
лише на читання.

Без `MCP_ACCESS_TOKENS` конектор вимкнено, і бот працює як раніше. Помилка в
змінних конектора лише вимикає його — у логах буде `Claude connector disabled: …`,
а бот стартує все одно.

### Увімкнути на Railway

1. **Токени.** Окремий для кожної людини, згенеруйте локально:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
   Токен потрапляє лише у Railway і в налаштування конектора.
2. **Variables:**
   - `MCP_ACCESS_TOKENS` = `serhii:<токен>,yulia:<токен>` — у меню змінної
     оберіть **Seal**, щоб значення більше не показувалось;
   - `MCP_PUBLIC_HOST` = `${{RAILWAY_PUBLIC_DOMAIN}}`.

   `PORT` Railway підставляє сам.
3. **Settings → Networking → Generate Domain.** Railway визначить порт
   автоматично; переконайтесь, що цільовий порт домену дорівнює `PORT`.
4. **Перевірка після деплою.** У логах —
   `Claude connector enabled on port … for serhii, yulia`. Далі:

   ```bash
   dig +short A <домен>                          # має бути IPv4: конектори Claude працюють лише через IPv4
   curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<домен>/mcp   # 401
   read -rs MCP_TOKEN                            # вставте токен; в історію shell він не потрапить
   curl -s https://<домен>/mcp \
     -H "Authorization: Bearer $MCP_TOKEN" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
   ```

   Остання команда має повернути JSON із `"result"`.

### Підключити Claude

- **claude.ai** (Desktop і мобільний застосунок підхоплять конектор з акаунта):
  Settings → Connectors → Add custom connector. URL — `https://<домен>/mcp`,
  саме `/mcp`, без слеша в кінці. Вхід — «No sign-in», Request header
  `Authorization` зі значенням `Bearer <токен>`.
- **Claude Code** — лише в user scope, щоб токен не потрапив у репозиторій:

  ```bash
  claude mcp add --transport http --scope user family-budget https://<домен>/mcp \
    --header "Authorization: Bearer $MCP_TOKEN"
  ```

### Ротація токена

1. Згенеруйте новий токен і замініть старий у `MCP_ACCESS_TOKENS` — Railway
   перезапустить сервіс.
2. Видаліть конектор у Claude і додайте знову з новим токеном: налаштування
   авторизації в наявному конекторі не редагуються.

### Локально

У `.env` задайте `MCP_ACCESS_TOKENS=dev:<32+ символи>` і
`MCP_PUBLIC_HOST=localhost:8080`; `docker compose up` прокидає порт 8080. Не
запускайте локально бота з бойовим `TELEGRAM_BOT_TOKEN`, поки працює прод:
Telegram віддає оновлення лише одному процесу.

### Якщо Claude не підключається

| Рядок у логах | Що це означає |
|---|---|
| `MCP access denied: missing bearer token` | заголовок не дійшов: перевірте назву `Authorization` і префікс `Bearer ` у значенні |
| `MCP access denied: invalid bearer token` | токен не збігається з жодним у `MCP_ACCESS_TOKENS` |
| `Invalid Host header: …` | `MCP_PUBLIC_HOST` не дорівнює домену з цього рядка |
| `Invalid Origin header: …` | клієнт надсилає інший `Origin` — його треба додати в `allowed_origins` у `src/budget_bot/connector/server.py` |
| `Claude connector disabled: …` | змінні конектора задано з помилкою; причина — в тому ж рядку |

````

- [ ] **Step 3: README — таблиця «Конфіг»**

У таблиці розділу `## Конфіг` після рядка `RECENT_EXPENSES_LIMIT` додати:

```markdown
| `MCP_ACCESS_TOKENS` | ні | — | Токени Claude-конектора: `мітка:токен` через кому, токен ≥ 32 символи. Не задано — конектор вимкнено |
| `MCP_PUBLIC_HOST` | коли задано `MCP_ACCESS_TOKENS` | — | Домен, на який звертається Claude: `${{RAILWAY_PUBLIC_DOMAIN}}` на Railway, `localhost:8080` локально |
| `PORT` | ні | `8080` | Порт конектора; Railway підставляє сам |
```

- [ ] **Step 4: `.env.example`**

Додати в кінець `tg-bot/.env.example`:

```bash

# Claude-конектор (опційно; без MCP_ACCESS_TOKENS вимкнено). Див. README.
# Формат: мітка:токен через кому, токен щонайменше 32 символи. Згенерувати:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
# MCP_ACCESS_TOKENS=serhii:...,yulia:...
# Домен, на який звертається Claude; локально — localhost:8080
# MCP_PUBLIC_HOST=localhost:8080
# Порт конектора (Railway підставляє сам)
# PORT=8080
```

- [ ] **Step 5: `docker-compose.yml`**

`tg-bot/docker-compose.yml` (повністю):

```yaml
services:
  bot:
    build: .
    env_file: .env
    environment:
      DATABASE_PATH: /data/budget.sqlite3
    ports:
      - "8080:8080"  # Claude connector; unused unless MCP_ACCESS_TOKENS is set
    volumes:
      - budget-data:/data
    restart: unless-stopped

volumes:
  budget-data:
```

- [ ] **Step 6: `CLAUDE.md` — статус**

У `CLAUDE.md` у кінець розділу `## Статус` додати абзац:

```markdown

Claude-конектор (MCP-сервер лише для читання) живе в `tg-bot/src/budget_bot/connector/`
і працює в тому ж процесі, що й бот; вмикається змінною `MCP_ACCESS_TOKENS`.
Дизайн — `docs/superpowers/specs/2026-09-15-claude-mcp-connector-design.md`,
підключення й ротація токенів — розділ «Claude-конектор» у `tg-bot/README.md`.
```

- [ ] **Step 7: Фінальна перевірка**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests && git status --short`
Expected: усі тести проходять; лінт чистий; у `git status` лише чотири файли документації з цієї задачі.

- [ ] **Step 8: Commit**

```bash
git add README.md .env.example docker-compose.yml ../CLAUDE.md
git commit -m "docs: explain enabling and connecting the Claude connector"
```

---

## Після злиття: деплой і підключення

Виконується разом із користувачем, не субагентом: потрібні доступ до Railway, генерація токенів і налаштування Claude.

1. **Токени** — згенерувати локально для кожної людини; у чат не вставляти.
2. **Railway → Variables:** `MCP_ACCESS_TOKENS` (Seal), `MCP_PUBLIC_HOST=${{RAILWAY_PUBLIC_DOMAIN}}`.
3. **Railway → Networking → Generate Domain**; цільовий порт = `PORT`.
4. **Деплой.** Автодеплой після merge не спрацьовує, тому:
   `railway service source connect --repo serhii-skotarenko/family-budget --branch main --service family-budget`.
5. **Логи:** `Claude connector enabled on port … for serhii, yulia`, далі `Run polling for bot`.
6. **Перевірки** з розділу README «Увімкнути на Railway», крок 4: IPv4 A-запис, `401` без токена, `initialize` з токеном.
7. **Підключення:** claude.ai custom connector і Claude Code (README «Підключити Claude»).
8. **Перевірити на живому сервісі** (документація Railway цього не підтверджує):
   - `Invalid Host header: …` у логах → Railway передає `Host` не так, як очікуємо;
   - `Invalid Origin header: …` → бекенд claude.ai надсилає інший `Origin`; додати значення в `allowed_origins`.
9. **Приймальна перевірка:** у claude.ai спитати «Скільки ми витратили на Їжу з 1 по 14 вересня?» і звірити з `/report` за той самий довільний період у боті.
