# Phase 2 · A — Limits, One-Time Expenses, Anomalies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Додати в бота ліміти на тиждень/місяць (загальні й по категоріях) з прогресом і прогнозом, позначку «разова» для витрат і м'яке попередження про аномально велику суму.

**Architecture:** Одна міграція Alembic (`limits` + `expenses.is_one_time`). Уся логіка лімітів — у новому `services/limits.py`: append-only історія, вибір активного ліміту, прогрес без разових витрат, прогноз. Текст рендерить `formatting.py`, кнопки будує `bot/keyboards.py`, новий роутер `bot/handlers/limits.py` відповідає за `/setlimit` і `/limits`. Наявні `/add`, `/list`, `/report` доповнюються, а не переписуються.

**Tech Stack:** Python 3.12, aiogram 3, SQLAlchemy 2 async + aiosqlite, Alembic, pytest + pytest-asyncio, ruff + black.

**Spec:** `docs/superpowers/specs/2026-09-30-phase2-a-limits-one-time-design.md`

## Global Constraints

- **Джерело правди — специфікація.** Якщо план і специфікація розійдуться — зупинитися й спитати.
- **Гілка:** `feat/phase2-limits`. Усі команди — з каталогу `tg-bot/`: `.venv/bin/python -m pytest …`, `.venv/bin/ruff check src tests`, `.venv/bin/black --check src tests`.
- **Суми** — цілі гривні (`int`), лише UAH; ввід суми ліміту — через наявний `parse_amount`.
- **Час:** у БД — UTC-naive (`budget_bot.clock.utcnow`), межі періодів — календарні Europe/Kyiv через `periods.period_range`; тиждень Пн–Нд.
- **Ліміти:** рядки `limits` ніколи не оновлюються й не видаляються; зняття = новий рядок з `amount = NULL`. Ліміт діє на весь поточний період. `period_type` — лише `Period.WEEK` / `Period.MONTH`.
- **Разові витрати** входять у суми `/report`, але **не** входять у прогрес, прогноз, попередження лімітів і в медіану аномалій.
- **Пороги:** попередження ≥80%, перевищення ≥100% (відсоток — `spent * 100 // amount`); аномалія — `amount > 3 × медіана` останніх 20 регулярних витрат категорії, лише якщо їх ≥5.
- **Бот не пише першим:** усі нові повідомлення — відповіді на дію користувача.
- **HTML:** весь текст користувача (назви категорій) — через `html.escape`.
- **Мова:** код, докстрінги, commit-меседжі — англійською; тексти бота — українською. Conventional commits, кожен коміт закінчується рядком `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Форматування:** перед кожним комітом `.venv/bin/black src tests` (код тестів у плані може бути не вирівняний black'ом). Якщо `ruff` скаржиться на E501 для довгого рядкового літерала — розбити його неявною конкатенацією, не змінюючи значення.
- **Тести:** реальна SQLite in-memory (фікстура `session`), без моків БД; очікувані числа пораховані вручну.
- **Міграція** застосовується автоматично при старті контейнера (`docker-entrypoint.sh` → `alembic upgrade head`); ручних кроків деплою немає.
- **Не запускати бота локально з бойовим токеном** з `tg-bot/.env` — прод на Railway уже опитує Telegram.
- MCP-конектор (`src/budget_bot/connector/`) у цьому плані **не змінюється**.

## Review Focus

1. **Ліміт без жодної витрати в періоді** — має показуватись у `/limits` з `0 ₴ / X — 0%` і прогнозом 0, без ділення на нуль (тест у Task 3 і Task 6).
2. **Назви власних категорій з HTML-символами** (`<b>…`) у `/limits`, у попередженнях після `/add` і в рядку ліміту `/report` — мають екрануватись (тести в Task 6 і Task 7).
3. **Подвійне натискання «Так, зняти»** — другий клік не додає ще один рядок історії, а відповідає «Ліміт уже знято.» (тест у Task 6).
4. **Витрата на межі періоду** (31.08 23:59 Києва vs 01.09) — не потрапляє в ліміт наступного місяця (тест у Task 3).
5. **Разові витрати не зсувають «типову» суму** — медіана аномалій рахується лише з регулярних (тест у Task 2).

## File Structure

Шляхи — відносно `tg-bot/`, крім `CLAUDE.md` у корені репозиторію.

| Файл | Дія | Відповідальність | Задача |
|---|---|---|---|
| `src/budget_bot/models.py` | змінити | + модель `Limit`, + `Expense.is_one_time` | 1 |
| `alembic/versions/0002_limits_and_one_time.py` | створити | міграція | 1 |
| `src/budget_bot/services/expenses.py` | змінити | `is_one_time` у `create_expense`, `set_one_time`, `typical_amount`, `is_anomalous` | 2 |
| `src/budget_bot/periods.py` | змінити | `LIMIT_PERIOD_TITLES`, `LIMIT_PERIOD_SHORT` | 3 |
| `src/budget_bot/services/limits.py` | створити | історія лімітів, прогрес, прогноз, статус | 3 |
| `src/budget_bot/services/reports.py` | змінити | `one_time`, `one_time_total`, `category_id` | 4 |
| `src/budget_bot/formatting.py` | змінити | звіт з лімітами; текст `/limits`; попередження; «разова» | 4, 5, 6, 7, 8 |
| `src/budget_bot/bot/handlers/reports.py` | змінити | передає прогрес лімітів у звіт | 4 |
| `src/budget_bot/bot/callbacks.py` | змінити | + `LimitCb` | 5 |
| `src/budget_bot/bot/keyboards.py` | змінити | клавіатури лімітів; перемикач «разова» | 5, 6, 7, 8 |
| `src/budget_bot/bot/handlers/limits.py` | створити | `/setlimit`, `/limits`, редагування, зняття | 5, 6 |
| `src/budget_bot/bot/handlers/__init__.py` | змінити | підключення роутера `limits` | 5 |
| `src/budget_bot/bot/handlers/common.py` | змінити | довідка | 6 |
| `src/budget_bot/__main__.py` | змінити | меню команд | 6 |
| `src/budget_bot/bot/handlers/add_expense.py` | змінити | перемикач, аномалія, попередження лімітів | 7 |
| `src/budget_bot/bot/handlers/expense_list.py` | змінити | перемикач «разова» на картці | 8 |
| `CLAUDE.md` | змінити | статус Phase 2 | 9 |
| `tests/test_models.py`, `tests/test_migrations.py` | змінити | модель і міграція | 1 |
| `tests/test_services_expenses.py` | змінити | разові, медіана | 2 |
| `tests/test_services_limits.py` | створити | логіка лімітів | 3 |
| `tests/test_services_reports.py`, `tests/test_formatting.py`, `tests/test_handlers_reports.py` | змінити | звіт | 4 |
| `tests/test_handlers_limits.py` | створити | `/setlimit`, `/limits` | 5, 6 |
| `tests/test_formatting_limits.py` | створити | текст `/limits` і попереджень | 6, 7 |
| `tests/test_handlers_add_expense.py` | змінити | `/add` | 7 |
| `tests/test_handlers_expense_list.py` | змінити | картка | 8 |

---

### Task 1: Schema — `Limit` model, `Expense.is_one_time`, migration 0002

**Files:**
- Modify: `src/budget_bot/models.py`
- Create: `alembic/versions/0002_limits_and_one_time.py`
- Test: `tests/test_models.py`, `tests/test_migrations.py`

**Interfaces:**
- Produces: `budget_bot.models.Limit` (`id`, `household_id`, `category_id: int | None`, `period_type: str`, `amount: int | None`, `effective_from`, `created_by_id`, `created_at`, `category: Category | None`); `Expense.is_one_time: bool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py` (add `Limit` to the `budget_bot.models` import):

```python
async def test_limit_persists_with_and_without_category(session, household, member, category):
    now = utcnow()
    session.add_all(
        [
            Limit(
                household_id=household.id,
                category_id=None,
                period_type="month",
                amount=50000,
                effective_from=now,
                created_by_id=member.id,
            ),
            Limit(
                household_id=household.id,
                category_id=category.id,
                period_type="week",
                amount=None,
                effective_from=now,
                created_by_id=member.id,
            ),
        ]
    )
    await session.commit()

    rows = list(await session.scalars(select(Limit).order_by(Limit.id)))
    assert rows[0].category is None and rows[0].amount == 50000
    assert rows[1].category.name == "Їжа" and rows[1].amount is None


async def test_expense_is_regular_by_default(session, household, member, category):
    expense = Expense(
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=100,
        created_at=utcnow(),
    )
    session.add(expense)
    await session.commit()
    await session.refresh(expense)

    assert expense.is_one_time is False
```

Append to `tests/test_migrations.py` (add `import sqlite3` at the top):

```python
def _alembic(db_path: Path, *args: str) -> None:
    result = subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), *args],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_PATH": str(db_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_0002_keeps_existing_expenses_regular_and_downgrades_cleanly(tmp_path):
    db_path = tmp_path / "old.sqlite3"
    _alembic(db_path, "upgrade", "0001")
    connection = sqlite3.connect(db_path)
    with connection:
        connection.execute(
            "INSERT INTO households (id, name, created_at) VALUES (1, 'Тест', '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO members (id, household_id, telegram_id, display_name, created_at) "
            "VALUES (1, 1, 111, 'Сергій', '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO categories (id, household_id, name, name_normalized, is_custom, created_at) "
            "VALUES (1, 1, 'Їжа', 'їжа', 0, '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO expenses (household_id, member_id, category_id, amount, created_at) "
            "VALUES (1, 1, 1, 250, '2026-09-01 10:00:00')"
        )
    connection.close()

    _alembic(db_path, "upgrade", "head")
    connection = sqlite3.connect(db_path)
    assert connection.execute("SELECT amount, is_one_time FROM expenses").fetchall() == [(250, 0)]
    connection.close()

    _alembic(db_path, "downgrade", "0001")
    connection = sqlite3.connect(db_path)
    columns = [row[1] for row in connection.execute("PRAGMA table_info(expenses)")]
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master")]
    amounts = connection.execute("SELECT amount FROM expenses").fetchall()
    connection.close()
    assert "is_one_time" not in columns
    assert "limits" not in tables
    assert amounts == [(250,)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py tests/test_migrations.py -v`
Expected: FAIL — `ImportError: cannot import name 'Limit'`, and alembic `Can't locate revision` for head having no `is_one_time`.

- [ ] **Step 3: Implement the model changes**

In `src/budget_bot/models.py`, add to `Expense` (after `amount`… keep it next to `description`):

```python
    # One-time expenses count in reports but never in limit progress or the
    # "typical amount" used for anomaly warnings.
    is_one_time: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
```

Append the new model at the end of the file:

```python
class Limit(Base):
    """A spending limit. Append-only: every change or removal inserts a new row.

    The active limit for a (period_type, category_id) pair is its latest row
    with ``effective_from <= now``; ``amount = NULL`` means the limit was
    removed. ``category_id = NULL`` is the household-wide limit.
    """

    __tablename__ = "limits"
    __table_args__ = (
        Index("ix_limits_lookup", "household_id", "period_type", "category_id", "effective_from"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    period_type: Mapped[str] = mapped_column(String(10))  # a budget_bot.periods.Period value
    amount: Mapped[int | None] = mapped_column(nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    category: Mapped[Category | None] = relationship(lazy="selectin")
```

- [ ] **Step 4: Write the migration**

Create `alembic/versions/0002_limits_and_one_time.py`:

```python
"""limits and one-time expenses

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "limits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("period_type", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_limits_lookup",
        "limits",
        ["household_id", "period_type", "category_id", "effective_from"],
    )
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(
            sa.Column("is_one_time", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("is_one_time")
    op.drop_index("ix_limits_lookup", table_name="limits")
    op.drop_table("limits")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_models.py tests/test_migrations.py -v`
Expected: PASS, including the existing `test_alembic_head_matches_models` (it catches any drift between the model and the migration).

- [ ] **Step 6: Run the full suite, lint, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`
Expected: all green.

```bash
git add src/budget_bot/models.py alembic/versions/0002_limits_and_one_time.py tests/test_models.py tests/test_migrations.py
git commit -m "feat: add limits table and one-time flag on expenses

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Expense service — one-time flag and typical amount

**Files:**
- Modify: `src/budget_bot/services/expenses.py`
- Test: `tests/test_services_expenses.py`

**Interfaces:**
- Consumes: `Expense.is_one_time` (Task 1).
- Produces:
  - `create_expense(..., is_one_time: bool = False) -> Expense`
  - `async set_one_time(session, expense: Expense, *, editor_id: int, value: bool) -> Expense`
  - `async typical_amount(session, household_id: int, category_id: int) -> int | None`
  - `is_anomalous(amount: int, typical: int | None) -> bool`
  - constants `ANOMALY_SAMPLE = 20`, `ANOMALY_MIN_SAMPLE = 5`, `ANOMALY_FACTOR = 3`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_services_expenses.py` (merge the imports with the existing ones):

```python
from datetime import timedelta

from budget_bot.clock import utcnow
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import (
    create_expense,
    is_anomalous,
    set_one_time,
    typical_amount,
)


async def _spend(session, household, member, category, amount, *, one_time=False, minutes_ago=0):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        is_one_time=one_time,
        created_at=utcnow() - timedelta(minutes=minutes_ago),
    )


async def test_create_expense_stores_one_time_flag(session, household, member, category):
    expense = await _spend(session, household, member, category, 100, one_time=True)

    assert expense.is_one_time is True


async def test_set_one_time_records_the_editor(session, household, member, partner, category):
    expense = await _spend(session, household, member, category, 100)

    updated = await set_one_time(session, expense, editor_id=partner.id, value=True)

    assert updated.is_one_time is True
    assert updated.updated_by_id == partner.id
    assert updated.updated_at is not None
    assert updated.member_id == member.id


async def test_typical_amount_needs_at_least_five_regular_expenses(
    session, household, member, category
):
    for amount in (100, 200, 300, 400):
        await _spend(session, household, member, category, amount)
    await _spend(session, household, member, category, 5000, one_time=True)

    assert await typical_amount(session, household.id, category.id) is None


async def test_typical_amount_is_the_median_of_regular_expenses(
    session, household, member, category
):
    for amount in (100, 200, 300, 400, 500, 600):
        await _spend(session, household, member, category, amount)
    await _spend(session, household, member, category, 90000, one_time=True)
    other = await add_category(session, household.id, "Кава")
    await _spend(session, household, member, other, 90000)

    # median(100..600) = (300 + 400) / 2 = 350; the one-time and the other
    # category are ignored.
    assert await typical_amount(session, household.id, category.id) == 350


async def test_typical_amount_uses_only_the_latest_twenty(session, household, member, category):
    for _ in range(20):
        await _spend(session, household, member, category, 100, minutes_ago=0)
    for _ in range(10):
        await _spend(session, household, member, category, 9000, minutes_ago=60)

    assert await typical_amount(session, household.id, category.id) == 100


def test_is_anomalous_threshold():
    assert is_anomalous(901, 300) is True
    assert is_anomalous(900, 300) is False
    assert is_anomalous(10_000, None) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_services_expenses.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_anomalous'`.

- [ ] **Step 3: Implement**

In `src/budget_bot/services/expenses.py`:

Add `from statistics import median` to the imports and these constants below the imports:

```python
# Anomaly warning: an amount above ANOMALY_FACTOR × the median of the latest
# ANOMALY_SAMPLE regular expenses in the category. Fewer than
# ANOMALY_MIN_SAMPLE regular expenses → no opinion.
ANOMALY_SAMPLE = 20
ANOMALY_MIN_SAMPLE = 5
ANOMALY_FACTOR = 3
```

Extend `create_expense` with the new keyword and pass it through:

```python
async def create_expense(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    category_id: int,
    amount: int,
    description: str | None = None,
    is_one_time: bool = False,
    created_at: datetime | None = None,
) -> Expense:
    expense = Expense(
        household_id=household_id,
        member_id=member_id,
        category_id=category_id,
        amount=amount,
        description=description,
        is_one_time=is_one_time,
        created_at=created_at or utcnow(),
    )
```

(the rest of the function is unchanged). Append:

```python
async def set_one_time(
    session: AsyncSession, expense: Expense, *, editor_id: int, value: bool
) -> Expense:
    """Toggle the one-time flag; recorded as an edit like any other."""
    expense.is_one_time = value
    expense.updated_by_id = editor_id
    expense.updated_at = utcnow()
    await session.flush()
    await session.refresh(expense)
    return expense


async def typical_amount(session: AsyncSession, household_id: int, category_id: int) -> int | None:
    amounts = list(
        await session.scalars(
            select(Expense.amount)
            .where(
                Expense.household_id == household_id,
                Expense.category_id == category_id,
                Expense.is_one_time.is_(False),
            )
            .order_by(Expense.created_at.desc(), Expense.id.desc())
            .limit(ANOMALY_SAMPLE)
        )
    )
    if len(amounts) < ANOMALY_MIN_SAMPLE:
        return None
    return round(median(amounts))


def is_anomalous(amount: int, typical: int | None) -> bool:
    return typical is not None and amount > ANOMALY_FACTOR * typical
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_services_expenses.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite, lint, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

```bash
git add src/budget_bot/services/expenses.py tests/test_services_expenses.py
git commit -m "feat: one-time flag and typical amount in the expense service

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Limits service — history, progress, forecast

**Files:**
- Modify: `src/budget_bot/periods.py`
- Create: `src/budget_bot/services/limits.py`
- Test: `tests/test_services_limits.py`

**Interfaces:**
- Consumes: `Limit`, `Expense.is_one_time` (Task 1); `periods.Period`, `period_range`, `to_kyiv`, `PeriodRange`.
- Produces (all in `budget_bot.services.limits` unless noted):
  - `periods.LIMIT_PERIOD_TITLES: dict[Period, str]` = `{WEEK: "тиждень", MONTH: "місяць"}`; `periods.LIMIT_PERIOD_SHORT` = `{WEEK: "тиж", MONTH: "міс"}`
  - `LIMIT_PERIODS = (Period.MONTH, Period.WEEK)` (display order), `WARN_PERCENT = 80`, `GENERAL_LIMIT_NAME = "Загальний"`
  - `class LimitStatus(StrEnum)`: `OK`, `WARN`, `OVER`
  - `@dataclass(frozen=True) LimitProgress(limit_id, period_type: Period, category_id: int | None, category_name: str | None, amount: int, spent: int, period: PeriodRange, day_index: int, days_in_period: int)` with properties `name -> str`, `percent -> int`, `remaining -> int`, `forecast -> int`, `status -> LimitStatus`
  - `forecast(spent: int, days_elapsed: int, days_in_period: int) -> int`
  - `limit_status(percent: int, forecast_amount: int, amount: int) -> LimitStatus`
  - `period_days(period: PeriodRange, now: datetime) -> tuple[int, int]` → `(day_index, days_in_period)`
  - `async active_limits(session, household_id, now) -> list[Limit]`
  - `async get_active_limit(session, household_id, period_type: Period, category_id: int | None, now) -> Limit | None`
  - `async set_limit(session, *, household_id, member_id, period_type: Period, category_id: int | None, amount: int, now: datetime | None = None) -> Limit`
  - `async remove_limit(session, *, household_id, member_id, period_type: Period, category_id: int | None, now: datetime | None = None) -> bool`
  - `async limit_progress(session, household_id, period_type: Period, now) -> list[LimitProgress]` — general first, then by category name
  - `async progress_for_expense(session, expense: Expense, now) -> list[LimitProgress]` — month then week; `[]` for a one-time expense

- [ ] **Step 1: Write the failing tests**

Create `tests/test_services_limits.py`:

```python
from datetime import timedelta

from budget_bot.periods import Period, period_range
from budget_bot.services.categories import add_category
from budget_bot.services.expenses import create_expense
from budget_bot.services.limits import (
    LimitStatus,
    active_limits,
    forecast,
    get_active_limit,
    limit_progress,
    limit_status,
    period_days,
    progress_for_expense,
    remove_limit,
    set_limit,
)
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)  # Thursday; week 12.10–18.10, month day 15 of 31


async def spend(session, household, member, category, amount, when=NOW, one_time=False):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        is_one_time=one_time,
        created_at=when,
    )


async def limit(session, household, member, period, category, amount, when=NOW):
    return await set_limit(
        session,
        household_id=household.id,
        member_id=member.id,
        period_type=period,
        category_id=category.id if category else None,
        amount=amount,
        now=when,
    )


def test_forecast():
    assert forecast(1000, 1, 31) == 31000
    assert forecast(1000, 31, 31) == 1000
    assert forecast(100, 3, 7) == 233  # 100 / 3 * 7 = 233.3
    assert forecast(0, 15, 31) == 0


def test_period_days():
    assert period_days(period_range(Period.MONTH, NOW), NOW) == (15, 31)
    assert period_days(period_range(Period.WEEK, NOW), NOW) == (4, 7)
    feb = kyiv(2026, 2, 10)
    assert period_days(period_range(Period.MONTH, feb), feb) == (10, 28)
    first_minute = kyiv(2026, 10, 1, 0, 5)
    assert period_days(period_range(Period.MONTH, first_minute), first_minute) == (1, 31)


def test_limit_status():
    assert limit_status(79, 900, 1000) is LimitStatus.OK
    assert limit_status(80, 900, 1000) is LimitStatus.WARN
    assert limit_status(50, 1001, 1000) is LimitStatus.WARN
    assert limit_status(100, 1000, 1000) is LimitStatus.OVER


async def test_active_limit_follows_history(session, household, member, category):
    t1 = NOW - timedelta(days=3)
    await limit(session, household, member, Period.MONTH, category, 1000, when=t1)
    await limit(session, household, member, Period.MONTH, category, 2000, when=t1 + timedelta(hours=1))

    active = await get_active_limit(session, household.id, Period.MONTH, category.id, NOW)
    assert active.amount == 2000

    removed = await remove_limit(
        session,
        household_id=household.id,
        member_id=member.id,
        period_type=Period.MONTH,
        category_id=category.id,
        now=t1 + timedelta(hours=2),
    )
    assert removed is True
    assert await get_active_limit(session, household.id, Period.MONTH, category.id, NOW) is None
    assert await active_limits(session, household.id, NOW) == []

    await limit(session, household, member, Period.MONTH, category, 3000, when=t1 + timedelta(hours=3))
    active = await get_active_limit(session, household.id, Period.MONTH, category.id, NOW)
    assert active.amount == 3000


async def test_limit_set_in_the_future_is_not_active_yet(session, household, member, category):
    await limit(session, household, member, Period.MONTH, category, 1000, when=NOW + timedelta(hours=1))

    assert await active_limits(session, household.id, NOW) == []


async def test_remove_without_active_limit_is_a_no_op(session, household, member, category):
    removed = await remove_limit(
        session,
        household_id=household.id,
        member_id=member.id,
        period_type=Period.WEEK,
        category_id=None,
        now=NOW,
    )

    assert removed is False


async def test_progress_counts_the_whole_period_regular_only(session, household, member, category):
    coffee = await add_category(session, household.id, "Кава")
    await spend(session, household, member, category, 3000, when=kyiv(2026, 10, 2))
    await spend(session, household, member, category, 5000, one_time=True)
    await spend(session, household, member, coffee, 700)
    await spend(session, household, member, category, 999, when=kyiv(2026, 9, 30, 23, 59))
    # Limits set mid-month still count expenses from 1 October.
    await limit(session, household, member, Period.MONTH, category, 10000)
    await limit(session, household, member, Period.MONTH, None, 20000)

    progress = await limit_progress(session, household.id, Period.MONTH, NOW)

    general, food = progress
    assert general.category_id is None and general.name == "Загальний"
    assert general.spent == 3700  # 3000 + 700; one-time and September excluded
    assert food.name == "Їжа"
    assert food.spent == 3000
    assert food.percent == 30
    assert food.remaining == 7000
    assert food.forecast == 6200  # 3000 / 15 * 31
    assert food.status is LimitStatus.OK


async def test_limit_without_spending_shows_zero(session, household, member, category):
    await limit(session, household, member, Period.WEEK, category, 1000)

    (progress,) = await limit_progress(session, household.id, Period.WEEK, NOW)

    assert (progress.spent, progress.percent, progress.forecast) == (0, 0, 0)
    assert progress.status is LimitStatus.OK


async def test_progress_for_expense_returns_only_relevant_limits(
    session, household, member, category
):
    coffee = await add_category(session, household.id, "Кава")
    await limit(session, household, member, Period.MONTH, category, 10000)
    await limit(session, household, member, Period.WEEK, None, 5000)
    await limit(session, household, member, Period.MONTH, coffee, 1000)
    expense = await spend(session, household, member, category, 4500)

    progress = await progress_for_expense(session, expense, NOW)

    assert [(p.period_type, p.category_id) for p in progress] == [
        (Period.MONTH, category.id),
        (Period.WEEK, None),
    ]
    assert progress[1].percent == 90


async def test_progress_for_one_time_expense_is_empty(session, household, member, category):
    await limit(session, household, member, Period.MONTH, category, 100)
    expense = await spend(session, household, member, category, 4500, one_time=True)

    assert await progress_for_expense(session, expense, NOW) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_services_limits.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.services.limits'`.

- [ ] **Step 3: Add period titles**

In `src/budget_bot/periods.py`, after `PERIOD_TITLES`:

```python
LIMIT_PERIOD_TITLES = {
    Period.WEEK: "тиждень",
    Period.MONTH: "місяць",
}

LIMIT_PERIOD_SHORT = {
    Period.WEEK: "тиж",
    Period.MONTH: "міс",
}
```

- [ ] **Step 4: Implement the service**

Create `src/budget_bot/services/limits.py`:

```python
"""Spending limits: append-only history, progress and forecast for the current period.

One-time expenses never count towards a limit (see the Phase 2 A spec).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.clock import utcnow
from budget_bot.models import Expense, Limit
from budget_bot.periods import Period, PeriodRange, period_range, to_kyiv

LIMIT_PERIODS = (Period.MONTH, Period.WEEK)
WARN_PERCENT = 80
GENERAL_LIMIT_NAME = "Загальний"


class LimitStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    OVER = "over"


def forecast(spent: int, days_elapsed: int, days_in_period: int) -> int:
    """Linear projection of the current pace onto the whole period."""
    return round(spent / days_elapsed * days_in_period)


def limit_status(percent: int, forecast_amount: int, amount: int) -> LimitStatus:
    if percent >= 100:
        return LimitStatus.OVER
    if percent >= WARN_PERCENT or forecast_amount > amount:
        return LimitStatus.WARN
    return LimitStatus.OK


def period_days(period: PeriodRange, now: datetime) -> tuple[int, int]:
    """(day_index, days_in_period) in Kyiv calendar days; today counts as elapsed."""
    first = to_kyiv(period.start).date()
    after_last = to_kyiv(period.end).date()
    today = to_kyiv(now).date()
    return (today - first).days + 1, (after_last - first).days


@dataclass(frozen=True)
class LimitProgress:
    limit_id: int
    period_type: Period
    category_id: int | None
    category_name: str | None
    amount: int
    spent: int
    period: PeriodRange
    day_index: int
    days_in_period: int

    @property
    def name(self) -> str:
        return self.category_name or GENERAL_LIMIT_NAME

    @property
    def percent(self) -> int:
        return self.spent * 100 // self.amount

    @property
    def remaining(self) -> int:
        return self.amount - self.spent

    @property
    def forecast(self) -> int:
        return forecast(self.spent, self.day_index, self.days_in_period)

    @property
    def status(self) -> LimitStatus:
        return limit_status(self.percent, self.forecast, self.amount)


async def _latest_rows(
    session: AsyncSession, household_id: int, now: datetime
) -> dict[tuple[str, int | None], Limit]:
    rows = await session.scalars(
        select(Limit)
        .where(Limit.household_id == household_id, Limit.effective_from <= now)
        .order_by(Limit.effective_from, Limit.id)
    )
    latest: dict[tuple[str, int | None], Limit] = {}
    for row in rows:
        latest[(row.period_type, row.category_id)] = row
    return latest


async def active_limits(session: AsyncSession, household_id: int, now: datetime) -> list[Limit]:
    latest = await _latest_rows(session, household_id, now)
    return [row for row in latest.values() if row.amount is not None]


async def get_active_limit(
    session: AsyncSession,
    household_id: int,
    period_type: Period,
    category_id: int | None,
    now: datetime,
) -> Limit | None:
    row = (await _latest_rows(session, household_id, now)).get((period_type.value, category_id))
    return row if row is not None and row.amount is not None else None


async def _append(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    period_type: Period,
    category_id: int | None,
    amount: int | None,
    now: datetime,
) -> Limit:
    row = Limit(
        household_id=household_id,
        category_id=category_id,
        period_type=period_type.value,
        amount=amount,
        effective_from=now,
        created_by_id=member_id,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def set_limit(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    period_type: Period,
    category_id: int | None,
    amount: int,
    now: datetime | None = None,
) -> Limit:
    return await _append(
        session,
        household_id=household_id,
        member_id=member_id,
        period_type=period_type,
        category_id=category_id,
        amount=amount,
        now=now or utcnow(),
    )


async def remove_limit(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    period_type: Period,
    category_id: int | None,
    now: datetime | None = None,
) -> bool:
    """Record the removal. Returns False when there was no active limit to remove."""
    now = now or utcnow()
    if await get_active_limit(session, household_id, period_type, category_id, now) is None:
        return False
    await _append(
        session,
        household_id=household_id,
        member_id=member_id,
        period_type=period_type,
        category_id=category_id,
        amount=None,
        now=now,
    )
    return True


async def limit_progress(
    session: AsyncSession, household_id: int, period_type: Period, now: datetime
) -> list[LimitProgress]:
    period = period_range(period_type, now)
    day_index, days_in_period = period_days(period, now)
    result = []
    for row in await active_limits(session, household_id, now):
        if row.period_type != period_type.value:
            continue
        query = select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.household_id == household_id,
            Expense.is_one_time.is_(False),
            Expense.created_at >= period.start,
            Expense.created_at < period.end,
        )
        if row.category_id is not None:
            query = query.where(Expense.category_id == row.category_id)
        result.append(
            LimitProgress(
                limit_id=row.id,
                period_type=period_type,
                category_id=row.category_id,
                category_name=row.category.name if row.category is not None else None,
                amount=row.amount,
                spent=int(await session.scalar(query)),
                period=period,
                day_index=day_index,
                days_in_period=days_in_period,
            )
        )
    result.sort(key=lambda p: (p.category_id is not None, (p.category_name or "").casefold()))
    return result


async def progress_for_expense(
    session: AsyncSession, expense: Expense, now: datetime
) -> list[LimitProgress]:
    """Limits this expense touches: its category's and the general ones, month then week."""
    if expense.is_one_time:
        return []
    result = []
    for period_type in LIMIT_PERIODS:
        result.extend(
            p
            for p in await limit_progress(session, expense.household_id, period_type, now)
            if p.category_id in (None, expense.category_id)
        )
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_services_limits.py -v`
Expected: PASS.

- [ ] **Step 6: Full suite, lint, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

```bash
git add src/budget_bot/periods.py src/budget_bot/services/limits.py tests/test_services_limits.py
git commit -m "feat: limits service with history, progress and forecast

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `/report` — one-time totals and limit lines

**Files:**
- Modify: `src/budget_bot/services/reports.py`, `src/budget_bot/formatting.py`, `src/budget_bot/bot/handlers/reports.py`
- Test: `tests/test_services_reports.py`, `tests/test_formatting.py`, `tests/test_handlers_reports.py`

**Interfaces:**
- Consumes: `LimitProgress`, `LimitStatus`, `LIMIT_PERIODS`, `limit_progress`, `set_limit` (Task 3); `create_expense(is_one_time=...)` (Task 2).
- Produces:
  - `CategoryTotal(name, amount, share, one_time: int = 0, category_id: int | None = None)`
  - `Report(period_label, total, by_category, by_member, one_time_total: int = 0)`
  - `format_report(report: Report, limits: Sequence[LimitProgress] = ()) -> str`
  - `formatting.STATUS_ICONS: dict[LimitStatus, str]` = `{OK: "", WARN: " ⚠️", OVER: " 🔴"}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_services_reports.py`:

```python
async def test_one_time_amounts_are_split_out(session, household, member, category):
    coffee = await add_category(session, household.id, "Кава")
    await add(session, household, member, category, 600)
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=400,
        is_one_time=True,
        created_at=NOW,
    )
    await add(session, household, member, coffee, 100)

    report = await build_report(session, household.id, WEEK)

    assert report.total == 1100
    assert report.one_time_total == 400
    food, drinks = report.by_category
    assert (food.name, food.amount, food.one_time, food.category_id) == (
        "Їжа",
        1000,
        400,
        category.id,
    )
    assert (drinks.name, drinks.one_time) == ("Кава", 0)
```

Append to `tests/test_formatting.py` (add imports `from budget_bot.periods import Period, period_range`, `from budget_bot.services.limits import LimitProgress`, `from tests.conftest import kyiv`):

```python
def _progress(category_id, name, amount, spent, period=Period.MONTH):
    now = kyiv(2026, 10, 15)
    return LimitProgress(
        limit_id=1,
        period_type=period,
        category_id=category_id,
        category_name=name,
        amount=amount,
        spent=spent,
        period=period_range(period, now),
        day_index=15,
        days_in_period=31,
    )


def test_report_shows_one_time_and_limit_lines():
    report = Report(
        period_label="поточний місяць (жовтень 2026)",
        total=58400,
        by_category=[
            CategoryTotal("<b>Діти</b>", 19921, 34.1, one_time=16962, category_id=7),
            CategoryTotal("Їжа", 38479, 65.9, category_id=1),
        ],
        by_member=[MemberTotal("Сергій", 58400)],
        one_time_total=16962,
    )
    limits = [
        _progress(None, None, 50000, 41438),
        _progress(7, "<b>Діти</b>", 4000, 2959),
    ]

    text = format_report(report, limits)

    assert "Разом: <b>58 400 ₴</b> (з них разових 16 962 ₴)" in text
    assert "  ліміт 50 000 ₴ — використано 82% ⚠️" in text
    assert "• &lt;b&gt;Діти&lt;/b&gt; — 19 921 ₴ (34.1%)" in text
    assert "  з них разових: 16 962 ₴" in text
    assert "  ліміт 4 000 ₴ — використано 73%" in text  # 2959*100//4000 = 73
    assert text.count("ліміт") == 2  # Їжа has no limit
```

Append to `tests/test_handlers_reports.py` (add imports `from budget_bot.periods import Period` and `from budget_bot.services.limits import set_limit`):

```python
async def _limit(session, household, member, period, category, amount):
    await set_limit(
        session,
        household_id=household.id,
        member_id=member.id,
        period_type=period,
        category_id=category.id,
        amount=amount,
    )


async def test_month_report_shows_the_month_limit_only(session, household, member, category):
    await make(session, household, member, category, 600)
    await _limit(session, household, member, Period.MONTH, category, 1000)
    await _limit(session, household, member, Period.WEEK, category, 5000)
    callback = FakeCallback()

    await cb_report(
        callback, callback_data=ReportCb(period="month"), session=session, member=member
    )

    text = callback.message.last_edit
    assert "ліміт 1 000 ₴ — використано 60%" in text
    assert "5 000" not in text


async def test_year_report_has_no_limit_lines(session, household, member, category):
    await make(session, household, member, category, 600)
    await _limit(session, household, member, Period.MONTH, category, 1000)
    callback = FakeCallback()

    await cb_report(callback, callback_data=ReportCb(period="year"), session=session, member=member)

    assert "ліміт" not in callback.message.last_edit
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_services_reports.py tests/test_formatting.py tests/test_handlers_reports.py -v`
Expected: FAIL — `AttributeError: 'Report' object has no attribute 'one_time_total'` / unexpected keyword `one_time`.

- [ ] **Step 3: Extend the report service**

In `src/budget_bot/services/reports.py`: import `case` from `sqlalchemy`; change the dataclasses and the category query:

```python
@dataclass(frozen=True)
class CategoryTotal:
    name: str
    amount: int
    share: float  # percent of the period total, one decimal
    one_time: int = 0  # part of `amount` marked as one-time
    category_id: int | None = None


@dataclass(frozen=True)
class Report:
    period_label: str
    total: int
    by_category: list[CategoryTotal]
    by_member: list[MemberTotal]
    one_time_total: int = 0
```

In `build_report`, after the early return for `not total`:

```python
    one_time_total = await session.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            *scope, Expense.is_one_time.is_(True)
        )
    )
    category_rows = await session.execute(
        select(
            Category.id,
            Category.name,
            func.sum(Expense.amount),
            func.sum(case((Expense.is_one_time, Expense.amount), else_=0)),
        )
        .join(Category, Category.id == Expense.category_id)
        .where(*scope)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(Expense.amount).desc(), Category.name)
    )
```

and build the result:

```python
    return Report(
        period_label=period.label,
        total=int(total),
        by_category=[
            CategoryTotal(
                name=name,
                amount=int(amount),
                share=round(amount * 100 / total, 1),
                one_time=int(one_time),
                category_id=category_id,
            )
            for category_id, name, amount, one_time in category_rows.all()
        ],
        by_member=[
            MemberTotal(display_name=name, amount=int(amount)) for name, amount in member_rows.all()
        ],
        one_time_total=int(one_time_total),
    )
```

- [ ] **Step 4: Extend `format_report`**

In `src/budget_bot/formatting.py` add imports:

```python
from budget_bot.services.limits import LimitProgress, LimitStatus
```

Add below the imports:

```python
STATUS_ICONS = {LimitStatus.OK: "", LimitStatus.WARN: " ⚠️", LimitStatus.OVER: " 🔴"}


def _limit_usage_line(progress: LimitProgress) -> str:
    return (
        f"  ліміт {format_amount(progress.amount)} — використано {progress.percent}%"
        f"{STATUS_ICONS[progress.status]}"
    )
```

Replace `format_report`:

```python
def format_report(report: Report, limits: Sequence[LimitProgress] = ()) -> str:
    header = f"📊 <b>Звіт — {escape(report.period_label)}</b>"
    if report.total == 0:
        return f"{header}\n\nВитрат за цей період не знайдено."

    limit_by_category = {progress.category_id: progress for progress in limits}
    total_line = f"Разом: <b>{format_amount(report.total)}</b>"
    if report.one_time_total:
        total_line += f" (з них разових {format_amount(report.one_time_total)})"
    lines = [header, total_line]
    if None in limit_by_category:
        lines.append(_limit_usage_line(limit_by_category[None]))

    lines.extend(["", "<b>За категоріями:</b>"])
    for item in report.by_category:
        lines.append(f"• {escape(item.name)} — {format_amount(item.amount)} ({item.share:.1f}%)")
        if item.one_time:
            lines.append(f"  з них разових: {format_amount(item.one_time)}")
        if item.category_id is not None and item.category_id in limit_by_category:
            lines.append(_limit_usage_line(limit_by_category[item.category_id]))

    lines.extend(["", "<b>За учасниками:</b>"])
    lines.extend(
        f"• {escape(item.display_name)} — {format_amount(item.amount)}" for item in report.by_member
    )
    return "\n".join(lines)
```

- [ ] **Step 5: Pass limits from the handler**

In `src/budget_bot/bot/handlers/reports.py` import `from budget_bot.services.limits import LIMIT_PERIODS, limit_progress` and replace the body of `cb_report`:

```python
    now = utcnow()
    report_period = Period(callback_data.period)
    report = await build_report(session, member.household_id, period_range(report_period, now))
    limits = (
        await limit_progress(session, member.household_id, report_period, now)
        if report_period in LIMIT_PERIODS
        else []
    )
    await edit_or_answer(callback, format_report(report, limits))
    await callback.answer()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_services_reports.py tests/test_formatting.py tests/test_handlers_reports.py -v`
Expected: PASS (the pre-existing report tests keep passing thanks to the field defaults).

- [ ] **Step 7: Full suite, lint, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

```bash
git add src/budget_bot/services/reports.py src/budget_bot/formatting.py src/budget_bot/bot/handlers/reports.py tests/test_services_reports.py tests/test_formatting.py tests/test_handlers_reports.py
git commit -m "feat: one-time totals and limit usage in /report

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `/setlimit` dialog

**Files:**
- Modify: `src/budget_bot/bot/callbacks.py`, `src/budget_bot/bot/keyboards.py`, `src/budget_bot/formatting.py`, `src/budget_bot/bot/handlers/__init__.py`
- Create: `src/budget_bot/bot/handlers/limits.py`
- Test: `tests/test_handlers_limits.py`

**Interfaces:**
- Consumes: `set_limit`, `get_active_limit`, `GENERAL_LIMIT_NAME` (Task 3); `periods.LIMIT_PERIOD_TITLES`.
- Produces:
  - `LimitCb(action: str, period_type: str = "", category_id: int = 0)`, prefix `"lim"`; actions `"period" | "category" | "add" | "edit" | "delete" | "delete_yes"`; `category_id == 0` ⇔ general limit
  - `keyboards.limit_periods_keyboard()`, `keyboards.limit_categories_keyboard(period_type: Period, categories)`
  - `formatting.format_limit_saved(period_type: Period, name: str, amount: int, previous: int | None) -> str`
  - `handlers.limits`: `router`, `SetLimit` states (`period`, `category`, `amount`), `cmd_setlimit(message, state)`, `cb_add_limit(callback, state)`, `pick_limit_period(callback, callback_data, state, session, member)`, `pick_limit_category(callback, callback_data, state, session, member)`, `enter_limit_amount(message, state, session, member)`, helper `ask_limit_amount(callback, state, session, member, period_type, category_id, name)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handlers_limits.py`:

```python
from budget_bot.bot.callbacks import LimitCb
from budget_bot.bot.handlers.limits import (
    SetLimit,
    cmd_setlimit,
    enter_limit_amount,
    pick_limit_category,
    pick_limit_period,
)
from budget_bot.clock import utcnow
from budget_bot.periods import Period
from budget_bot.services.limits import active_limits, get_active_limit, set_limit
from tests.conftest import FakeCallback, FakeMessage


def buttons(kwargs) -> list[str]:
    return [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]


async def run_setlimit(session, member, state, period: str, category_id: int, amount: str):
    await cmd_setlimit(FakeMessage(text="/setlimit"), state=state)
    await pick_limit_period(
        FakeCallback(),
        callback_data=LimitCb(action="period", period_type=period),
        state=state,
        session=session,
        member=member,
    )
    await pick_limit_category(
        FakeCallback(),
        callback_data=LimitCb(action="category", period_type=period, category_id=category_id),
        state=state,
        session=session,
        member=member,
    )
    reply = FakeMessage(text=amount)
    await enter_limit_amount(reply, state=state, session=session, member=member)
    return reply


async def test_setlimit_offers_week_and_month(state):
    message = FakeMessage(text="/setlimit")

    await cmd_setlimit(message, state=state)

    assert await state.get_state() == SetLimit.period
    labels = buttons(message.replies[-1][1])
    assert "Тиждень" in labels and "Місяць" in labels


async def test_category_step_offers_general_first(session, member, category, state):
    await cmd_setlimit(FakeMessage(text="/setlimit"), state=state)
    callback = FakeCallback()

    await pick_limit_period(
        callback,
        callback_data=LimitCb(action="period", period_type="month"),
        state=state,
        session=session,
        member=member,
    )

    assert await state.get_state() == SetLimit.category
    labels = buttons(callback.message.edits[-1][1])
    assert labels[0] == "🌐 Загальний"
    assert "Їжа" in labels


async def test_full_flow_saves_a_category_limit(session, member, category, state):
    reply = await run_setlimit(session, member, state, "month", category.id, "12 000")

    assert await state.get_state() is None
    saved = await get_active_limit(session, member.household_id, Period.MONTH, category.id, utcnow())
    assert saved.amount == 12000
    assert saved.created_by_id == member.id
    assert reply.last_reply == "✅ Ліміт на місяць · Їжа: <b>12 000 ₴</b>"


async def test_general_limit_and_previous_amount(session, member, category, state):
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=Period.WEEK,
        category_id=None,
        amount=10000,
    )

    reply = await run_setlimit(session, member, state, "week", 0, "8000")

    assert reply.last_reply == (
        "✅ Ліміт на тиждень · Загальний: <b>8 000 ₴</b> (було 10 000 ₴)"
    )


async def test_amount_prompt_shows_current_limit(session, member, category, state):
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=Period.MONTH,
        category_id=category.id,
        amount=5000,
    )
    await state.set_state(SetLimit.category)
    callback = FakeCallback()

    await pick_limit_category(
        callback,
        callback_data=LimitCb(action="category", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )

    assert await state.get_state() == SetLimit.amount
    assert "(зараз: 5 000 ₴)" in callback.message.last_reply


async def test_invalid_amount_keeps_the_step(session, member, category, state):
    await state.set_state(SetLimit.amount)
    await state.update_data(period_type="month", category_id=None, category_name="Загальний")
    message = FakeMessage(text="0")

    await enter_limit_amount(message, state=state, session=session, member=member)

    assert await state.get_state() == SetLimit.amount
    assert "більшою за нуль" in message.last_reply
    assert await active_limits(session, member.household_id, utcnow()) == []


async def test_unknown_category_is_reported(session, member, category, state):
    await state.set_state(SetLimit.category)
    callback = FakeCallback()

    await pick_limit_category(
        callback,
        callback_data=LimitCb(action="category", period_type="month", category_id=9999),
        state=state,
        session=session,
        member=member,
    )

    assert await state.get_state() == SetLimit.category
    assert callback.answers[-1][1] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_handlers_limits.py -v`
Expected: FAIL — `ImportError: cannot import name 'LimitCb'`.

- [ ] **Step 3: Callback, keyboards, saved-text formatter**

Append to `src/budget_bot/bot/callbacks.py`:

```python
class LimitCb(CallbackData, prefix="lim"):
    action: str  # "period" | "category" | "add" | "edit" | "delete" | "delete_yes"
    period_type: str = ""  # a budget_bot.periods.Period value (week | month)
    category_id: int = 0  # 0 = the household-wide limit
```

In `src/budget_bot/bot/keyboards.py`: add `LimitCb` to the callbacks import, import `LIMIT_PERIOD_TITLES` from `budget_bot.periods` and `GENERAL_LIMIT_NAME` from `budget_bot.services.limits`; append:

```python
def limit_periods_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in (Period.WEEK, Period.MONTH):
        builder.button(
            text=LIMIT_PERIOD_TITLES[period].capitalize(),
            callback_data=LimitCb(action="period", period_type=period.value),
        )
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2, 1)
    return builder.as_markup()


def limit_categories_keyboard(
    period_type: Period, categories: Sequence[Category]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"🌐 {GENERAL_LIMIT_NAME}",
        callback_data=LimitCb(action="category", period_type=period_type.value, category_id=0),
    )
    for item in categories:
        builder.button(
            text=item.name,
            callback_data=LimitCb(
                action="category", period_type=period_type.value, category_id=item.id
            ),
        )
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(1, 2)
    return builder.as_markup()
```

In `src/budget_bot/formatting.py` add `from budget_bot.periods import LIMIT_PERIOD_TITLES, Period` (merge with the existing periods import) and append:

```python
def format_limit_saved(period_type: Period, name: str, amount: int, previous: int | None) -> str:
    text = (
        f"✅ Ліміт на {LIMIT_PERIOD_TITLES[period_type]} · {escape(name)}: "
        f"<b>{format_amount(amount)}</b>"
    )
    if previous is not None:
        text += f" (було {format_amount(previous)})"
    return text
```

- [ ] **Step 4: The handler module**

Create `src/budget_bot/bot/handlers/limits.py`:

```python
"""/setlimit: period → category (or general) → amount. /limits lives here too (Task 6)."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.amounts import AmountError, format_amount, parse_amount
from budget_bot.bot.callbacks import LimitCb
from budget_bot.bot.keyboards import (
    cancel_keyboard,
    limit_categories_keyboard,
    limit_periods_keyboard,
)
from budget_bot.bot.predicates import NOT_A_COMMAND
from budget_bot.bot.replies import edit_or_answer
from budget_bot.clock import utcnow
from budget_bot.formatting import format_limit_saved
from budget_bot.models import Member
from budget_bot.periods import LIMIT_PERIOD_TITLES, Period
from budget_bot.services.categories import get_category, list_categories
from budget_bot.services.limits import GENERAL_LIMIT_NAME, get_active_limit, set_limit

router = Router(name="limits")

PERIOD_PROMPT = "Оберіть період ліміту:"


class SetLimit(StatesGroup):
    period = State()
    category = State()
    amount = State()


@router.message(Command("setlimit"))
async def cmd_setlimit(message: Message, state: FSMContext) -> None:
    await state.set_state(SetLimit.period)
    await state.set_data({})
    await message.answer(PERIOD_PROMPT, reply_markup=limit_periods_keyboard())


@router.callback_query(LimitCb.filter(F.action == "add"))
async def cb_add_limit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SetLimit.period)
    await state.set_data({})
    await callback.message.answer(PERIOD_PROMPT, reply_markup=limit_periods_keyboard())
    await callback.answer()


@router.callback_query(SetLimit.period, LimitCb.filter(F.action == "period"))
async def pick_limit_period(
    callback: CallbackQuery,
    callback_data: LimitCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    period_type = Period(callback_data.period_type)
    await state.set_state(SetLimit.category)
    categories = await list_categories(session, member.household_id)
    await edit_or_answer(
        callback,
        f"Ліміт на {LIMIT_PERIOD_TITLES[period_type]}. Оберіть категорію:",
        reply_markup=limit_categories_keyboard(period_type, categories),
    )
    await callback.answer()


@router.callback_query(SetLimit.category, LimitCb.filter(F.action == "category"))
async def pick_limit_category(
    callback: CallbackQuery,
    callback_data: LimitCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    period_type = Period(callback_data.period_type)
    if callback_data.category_id == 0:
        category_id, name = None, GENERAL_LIMIT_NAME
    else:
        category = await get_category(session, member.household_id, callback_data.category_id)
        if category is None:
            await callback.answer("Категорію не знайдено. Оберіть іншу.", show_alert=True)
            return
        category_id, name = category.id, category.name

    await ask_limit_amount(callback, state, session, member, period_type, category_id, name)
    await callback.answer()


async def ask_limit_amount(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
    period_type: Period,
    category_id: int | None,
    name: str,
) -> None:
    """Move to the amount step; shared by /setlimit and the ✏️ button in /limits."""
    await state.set_state(SetLimit.amount)
    await state.set_data(
        {"period_type": period_type.value, "category_id": category_id, "category_name": name}
    )
    current = await get_active_limit(session, member.household_id, period_type, category_id, utcnow())
    hint = f" (зараз: {format_amount(current.amount)})" if current is not None else ""
    await callback.message.answer(
        f"Ліміт на {LIMIT_PERIOD_TITLES[period_type]} · <b>{escape(name)}</b>\n\n"
        f"Введіть суму ліміту в гривнях{hint}:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SetLimit.amount, NOT_A_COMMAND)
async def enter_limit_amount(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        amount = parse_amount(message.text or "")
    except AmountError as error:
        await message.answer(f"⚠️ {escape(str(error))}", reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    period_type = Period(data["period_type"])
    category_id = data["category_id"]
    previous = await get_active_limit(
        session, member.household_id, period_type, category_id, utcnow()
    )
    await state.clear()
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=period_type,
        category_id=category_id,
        amount=amount,
    )
    await message.answer(
        format_limit_saved(
            period_type,
            data["category_name"],
            amount,
            previous.amount if previous is not None else None,
        )
    )
```

In `src/budget_bot/bot/handlers/__init__.py` add `limits` to the import list and `limits.router,` right after `reports.router,` (before `fallback.router`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_handlers_limits.py tests/test_dispatch_smoke.py -v`
Expected: PASS.

- [ ] **Step 6: Full suite, lint, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

```bash
git add src/budget_bot/bot/callbacks.py src/budget_bot/bot/keyboards.py src/budget_bot/formatting.py src/budget_bot/bot/handlers/limits.py src/budget_bot/bot/handlers/__init__.py tests/test_handlers_limits.py
git commit -m "feat: /setlimit dialog

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `/limits` — progress view, edit and remove, help and command menu

**Files:**
- Modify: `src/budget_bot/formatting.py`, `src/budget_bot/bot/keyboards.py`, `src/budget_bot/bot/handlers/limits.py`, `src/budget_bot/bot/handlers/common.py`, `src/budget_bot/__main__.py`
- Test: `tests/test_formatting_limits.py`, `tests/test_handlers_limits.py`, `tests/test_handlers_common.py`

**Interfaces:**
- Consumes: `LimitProgress`, `LimitStatus`, `LIMIT_PERIODS`, `limit_progress`, `get_active_limit`, `remove_limit` (Task 3); `ask_limit_amount`, `LimitCb` (Task 5); `STATUS_ICONS` (Task 4).
- Produces:
  - `formatting.EMPTY_LIMITS_TEXT`, `formatting.format_limits(progress: Sequence[LimitProgress]) -> str`
  - `keyboards.limits_keyboard(progress)`, `keyboards.limit_delete_confirm_keyboard(period_type: Period, category_id: int)`
  - handlers `cmd_limits(message, state, session, member)`, `cb_edit_limit`, `cb_ask_delete_limit`, `cb_delete_limit` (all callbacks: `callback, callback_data, state, session, member`)
  - `LIMIT_GONE_TEXT = "Ліміт уже знято."`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_formatting_limits.py`:

```python
from budget_bot.formatting import EMPTY_LIMITS_TEXT, format_limits
from budget_bot.periods import Period, period_range
from budget_bot.services.limits import LimitProgress, period_days
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)


def progress(period, category_id, name, amount, spent):
    period_bounds = period_range(period, NOW)
    day_index, days = period_days(period_bounds, NOW)
    return LimitProgress(
        limit_id=1,
        period_type=period,
        category_id=category_id,
        category_name=name,
        amount=amount,
        spent=spent,
        period=period_bounds,
        day_index=day_index,
        days_in_period=days,
    )


def test_empty():
    assert format_limits([]) == EMPTY_LIMITS_TEXT


def test_month_and_week_sections():
    text = format_limits(
        [
            progress(Period.MONTH, None, None, 50000, 38000),
            progress(Period.MONTH, 1, "Їжа", 12000, 9800),
            progress(Period.WEEK, 2, "<b>Кава</b>", 1000, 1300),
        ]
    )

    assert "<b>Місяць (жовтень, день 15 з 31):</b>" in text
    # 38000*100//50000 = 76; forecast 38000/15*31 = 78533 > 50000 → ⚠️
    assert (
        "• Загальний: 38 000 ₴ / 50 000 ₴ — 76%, "
        "лишилось 12 000 ₴\n  прогноз: 78 533 ₴ ⚠️"
    ) in text
    # 9800*100//12000 = 81 → ⚠️ on the usage line
    assert "• Їжа: 9 800 ₴ / 12 000 ₴ — 81% ⚠️, лишилось 2 200 ₴" in text
    assert "<b>Тиждень (12.10–18.10, день 4 з 7):</b>" in text
    assert (
        "• &lt;b&gt;Кава&lt;/b&gt;: 1 300 ₴ / 1 000 ₴ — 130% 🔴 "
        "перевищено на 300 ₴"
    ) in text
    assert text.index("Місяць") < text.index("Тиждень")


def test_exactly_at_limit_says_exhausted():
    text = format_limits([progress(Period.WEEK, None, None, 1000, 1000)])

    assert "— 100% 🔴 ліміт вичерпано" in text


def test_zero_spending():
    text = format_limits([progress(Period.MONTH, None, None, 1000, 0)])

    assert "0 ₴ / 1 000 ₴ — 0%, лишилось 1 000 ₴\n  прогноз: 0 ₴" in text
```

Append to `tests/test_handlers_limits.py` (extend the imports with `cb_ask_delete_limit`, `cb_delete_limit`, `cb_edit_limit`, `cmd_limits` from `budget_bot.bot.handlers.limits`, and `from budget_bot.services.expenses import create_expense`):

```python
async def _set(session, member, period, category_id, amount):
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=period,
        category_id=category_id,
        amount=amount,
    )


async def test_limits_empty(session, member, state):
    message = FakeMessage(text="/limits")

    await cmd_limits(message, state=state, session=session, member=member)

    assert "Лімітів ще немає" in message.last_reply
    assert buttons(message.replies[-1][1]) == ["➕ Додати ліміт"]


async def test_limits_shows_progress_and_buttons(session, household, member, category, state):
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=9800,
    )
    await _set(session, member, Period.MONTH, category.id, 12000)
    await _set(session, member, Period.WEEK, None, 20000)
    message = FakeMessage(text="/limits")

    await cmd_limits(message, state=state, session=session, member=member)

    assert "9 800 ₴ / 12 000 ₴" in message.last_reply
    assert buttons(message.replies[-1][1]) == [
        "✏️ Їжа · міс",
        "🗑",
        "✏️ Загальний · тиж",
        "🗑",
        "➕ Додати ліміт",
    ]


async def test_edit_button_jumps_to_amount_step(session, member, category, state):
    await _set(session, member, Period.MONTH, category.id, 12000)
    callback = FakeCallback()

    await cb_edit_limit(
        callback,
        callback_data=LimitCb(action="edit", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )

    assert await state.get_state() == SetLimit.amount
    assert "(зараз: 12 000 ₴)" in callback.message.last_reply

    reply = FakeMessage(text="15000")
    await enter_limit_amount(reply, state=state, session=session, member=member)
    assert "(було 12 000 ₴)" in reply.last_reply


async def test_delete_asks_then_removes_and_rerenders(session, member, category, state):
    await _set(session, member, Period.MONTH, category.id, 12000)
    ask = FakeCallback()

    await cb_ask_delete_limit(
        ask,
        callback_data=LimitCb(action="delete", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    assert "Зняти ліміт «Їжа · місяць»?" in ask.message.last_reply

    confirm = FakeCallback()
    await cb_delete_limit(
        confirm,
        callback_data=LimitCb(action="delete_yes", period_type="month", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    assert confirm.message.last_edit.startswith("🗑 Ліміт знято.")
    assert "Лімітів ще немає" in confirm.message.last_edit
    assert await active_limits(session, member.household_id, utcnow()) == []


async def test_double_tap_delete_reports_already_removed(session, member, category, state):
    await _set(session, member, Period.MONTH, None, 12000)
    data = LimitCb(action="delete_yes", period_type="month", category_id=0)
    await cb_delete_limit(
        FakeCallback(), callback_data=data, state=state, session=session, member=member
    )
    second = FakeCallback()

    await cb_delete_limit(second, callback_data=data, state=state, session=session, member=member)

    assert second.answers[-1] == ("Ліміт уже знято.", True)
    assert second.message.edits == []


async def test_edit_of_removed_limit_is_stale(session, member, category, state):
    callback = FakeCallback()

    await cb_edit_limit(
        callback,
        callback_data=LimitCb(action="edit", period_type="week", category_id=0),
        state=state,
        session=session,
        member=member,
    )

    assert callback.answers[-1] == ("Ліміт уже знято.", True)
    assert await state.get_state() is None
```

Append to `tests/test_handlers_common.py`:

```python
def test_help_and_command_menu_list_limits():
    from budget_bot.__main__ import BOT_COMMANDS
    from budget_bot.bot.handlers.common import HELP_TEXT

    assert "/limits" in HELP_TEXT and "/setlimit" in HELP_TEXT
    commands = {command.command for command in BOT_COMMANDS}
    assert {"limits", "setlimit"} <= commands
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_formatting_limits.py tests/test_handlers_limits.py tests/test_handlers_common.py -v`
Expected: FAIL — `ImportError: cannot import name 'EMPTY_LIMITS_TEXT'`.

- [ ] **Step 3: `/limits` text**

In `src/budget_bot/formatting.py` extend the imports: `MONTHS_UK`, `to_kyiv` from `budget_bot.periods`; `LIMIT_PERIODS` from `budget_bot.services.limits`; `from datetime import timedelta`. Append:

```python
EMPTY_LIMITS_TEXT = "Лімітів ще немає. Додати — /setlimit"


def _limits_section_title(progress: LimitProgress) -> str:
    first = to_kyiv(progress.period.start).date()
    day = f"день {progress.day_index} з {progress.days_in_period}"
    if progress.period_type is Period.MONTH:
        return f"<b>Місяць ({MONTHS_UK[first.month - 1]}, {day}):</b>"
    last = to_kyiv(progress.period.end).date() - timedelta(days=1)
    return f"<b>Тиждень ({first:%d.%m}–{last:%d.%m}, {day}):</b>"


def _limit_line(progress: LimitProgress) -> str:
    line = (
        f"• {escape(progress.name)}: {format_amount(progress.spent)} / "
        f"{format_amount(progress.amount)} — {progress.percent}%"
    )
    if progress.status is LimitStatus.OVER:
        over = progress.spent - progress.amount
        line += f" 🔴 перевищено на {format_amount(over)}" if over else " 🔴 ліміт вичерпано"
        return line
    if progress.percent >= WARN_PERCENT:
        line += " ⚠️"
    line += f", лишилось {format_amount(progress.remaining)}"
    forecast_icon = " ⚠️" if progress.forecast > progress.amount else ""
    return f"{line}\n  прогноз: {format_amount(progress.forecast)}{forecast_icon}"


def format_limits(progress: Sequence[LimitProgress]) -> str:
    if not progress:
        return EMPTY_LIMITS_TEXT
    lines = ["📊 <b>Ліміти</b>"]
    for period_type in LIMIT_PERIODS:
        items = [item for item in progress if item.period_type is period_type]
        if not items:
            continue
        lines.extend(["", _limits_section_title(items[0])])
        lines.extend(_limit_line(item) for item in items)
    return "\n".join(lines)
```

(add `WARN_PERCENT` to the `budget_bot.services.limits` import).

- [ ] **Step 4: Keyboards**

In `src/budget_bot/bot/keyboards.py` add `LIMIT_PERIOD_SHORT` to the periods import and `LimitProgress` to the limits import; append:

```python
def limits_keyboard(progress: Sequence[LimitProgress]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in progress:
        target = {"period_type": item.period_type.value, "category_id": item.category_id or 0}
        builder.button(
            text=f"✏️ {item.name} · {LIMIT_PERIOD_SHORT[item.period_type]}",
            callback_data=LimitCb(action="edit", **target),
        )
        builder.button(text="🗑", callback_data=LimitCb(action="delete", **target))
    builder.button(text="➕ Додати ліміт", callback_data=LimitCb(action="add"))
    builder.adjust(*([2] * len(progress)), 1)
    return builder.as_markup()


def limit_delete_confirm_keyboard(period_type: Period, category_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗑 Так, зняти",
        callback_data=LimitCb(
            action="delete_yes", period_type=period_type.value, category_id=category_id
        ),
    )
    builder.button(text="↩️ Ні", callback_data=FlowCb(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()
```

- [ ] **Step 5: Handlers**

In `src/budget_bot/bot/handlers/limits.py`: update the module docstring to `"""/setlimit dialog and the /limits view with edit and remove buttons."""`; extend imports with `limit_delete_confirm_keyboard`, `limits_keyboard` (keyboards), `format_limits` (formatting), `LIMIT_PERIODS`, `limit_progress`, `remove_limit` (services.limits), `from aiogram.types import InlineKeyboardMarkup`. Append:

```python
LIMIT_GONE_TEXT = "Ліміт уже знято."


async def _render_limits(
    session: AsyncSession, household_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    now = utcnow()
    progress = [
        item
        for period_type in LIMIT_PERIODS
        for item in await limit_progress(session, household_id, period_type, now)
    ]
    return format_limits(progress), limits_keyboard(progress)


@router.message(Command("limits"))
async def cmd_limits(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    await state.clear()
    text, keyboard = await _render_limits(session, member.household_id)
    await message.answer(text, reply_markup=keyboard)


async def _target(
    callback_data: LimitCb, session: AsyncSession, member: Member
) -> tuple[Period, int | None, str] | None:
    """(period, category_id, display name) of the button's limit, or None if it is gone."""
    period_type = Period(callback_data.period_type)
    category_id = callback_data.category_id or None
    active = await get_active_limit(session, member.household_id, period_type, category_id, utcnow())
    if active is None:
        return None
    name = active.category.name if active.category is not None else GENERAL_LIMIT_NAME
    return period_type, category_id, name


@router.callback_query(LimitCb.filter(F.action == "edit"))
async def cb_edit_limit(
    callback: CallbackQuery,
    callback_data: LimitCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    target = await _target(callback_data, session, member)
    if target is None:
        await callback.answer(LIMIT_GONE_TEXT, show_alert=True)
        return
    period_type, category_id, name = target
    await ask_limit_amount(callback, state, session, member, period_type, category_id, name)
    await callback.answer()


@router.callback_query(LimitCb.filter(F.action == "delete"))
async def cb_ask_delete_limit(
    callback: CallbackQuery,
    callback_data: LimitCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    target = await _target(callback_data, session, member)
    if target is None:
        await callback.answer(LIMIT_GONE_TEXT, show_alert=True)
        return
    period_type, category_id, name = target
    await callback.message.answer(
        f"Зняти ліміт «{escape(name)} · {LIMIT_PERIOD_TITLES[period_type]}»?",
        reply_markup=limit_delete_confirm_keyboard(period_type, category_id or 0),
    )
    await callback.answer()


@router.callback_query(LimitCb.filter(F.action == "delete_yes"))
async def cb_delete_limit(
    callback: CallbackQuery,
    callback_data: LimitCb,
    state: FSMContext,
    session: AsyncSession,
    member: Member,
) -> None:
    removed = await remove_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=Period(callback_data.period_type),
        category_id=callback_data.category_id or None,
    )
    if not removed:
        await callback.answer(LIMIT_GONE_TEXT, show_alert=True)
        return
    text, keyboard = await _render_limits(session, member.household_id)
    await edit_or_answer(callback, f"🗑 Ліміт знято.\n\n{text}", reply_markup=keyboard)
    await callback.answer()
```

- [ ] **Step 6: Help text and command menu**

In `src/budget_bot/bot/handlers/common.py`, `HELP_TEXT`, insert after the `/report` line:

```python
    "🎯 /limits — ліміти, прогрес і прогноз\n"
    "🎯 /setlimit — встановити ліміт на тиждень / місяць\n"
```

In `src/budget_bot/__main__.py`, `BOT_COMMANDS`, insert after `report`:

```python
    BotCommand(command="limits", description="Ліміти та прогрес"),
    BotCommand(command="setlimit", description="Встановити ліміт"),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_formatting_limits.py tests/test_handlers_limits.py tests/test_handlers_common.py -v`
Expected: PASS.

- [ ] **Step 8: Full suite, lint, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

```bash
git add src/budget_bot/formatting.py src/budget_bot/bot/keyboards.py src/budget_bot/bot/handlers/limits.py src/budget_bot/bot/handlers/common.py src/budget_bot/__main__.py tests/test_formatting_limits.py tests/test_handlers_limits.py tests/test_handlers_common.py
git commit -m "feat: /limits view with edit and remove

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `/add` — one-time toggle, anomaly warning, limit alerts

**Files:**
- Modify: `src/budget_bot/bot/keyboards.py`, `src/budget_bot/formatting.py`, `src/budget_bot/bot/handlers/add_expense.py`
- Test: `tests/test_handlers_add_expense.py`, `tests/test_formatting_limits.py`, `tests/test_formatting.py`

**Interfaces:**
- Consumes: `typical_amount`, `is_anomalous`, `create_expense(is_one_time=...)` (Task 2); `progress_for_expense`, `WARN_PERCENT`, `set_limit` (Task 3).
- Produces:
  - `confirm_keyboard(is_one_time: bool = False)` — toggle button `FlowCb(action="toggle_one_time")` above save/cancel
  - `formatting.format_limit_alert(progress: LimitProgress) -> str`
  - `format_expense_line` appends `· разова` for one-time expenses
  - handler `toggle_one_time(callback, state)`; FSM data keys `typical: int | None`, `is_one_time: bool`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_formatting_limits.py` (add `format_limit_alert` to the formatting import):

```python
def test_limit_alerts():
    warn = progress(Period.MONTH, 1, "<i>Їжа</i>", 12000, 9800)
    over = progress(Period.WEEK, None, None, 10000, 10400)

    assert format_limit_alert(warn) == (
        "⚠️ &lt;i&gt;Їжа&lt;/i&gt; (місяць): 9 800 ₴ / 12 000 ₴ — 81%"
    )
    assert format_limit_alert(over) == (
        "🔴 Загальний (тиждень): 10 400 ₴ / 10 000 ₴ — перевищено на 400 ₴"
    )
```

Append to `tests/test_formatting.py`:

```python
async def test_expense_line_marks_one_time(session, household, member, category):
    expense = await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=250,
        is_one_time=True,
        created_at=datetime(2026, 9, 7, 9, 0),
    )

    assert format_expense_line(expense) == "07.09 · 250 ₴ · Їжа · Сергій · разова"
```

(make sure `datetime` and `create_expense` are imported in that module; add them if missing.)

Append to `tests/test_handlers_add_expense.py` (extend imports: `toggle_one_time` from the handler module; `from budget_bot.periods import Period`; `from budget_bot.services.expenses import create_expense`; `from budget_bot.services.limits import set_limit`):

```python
def labels(kwargs) -> list[str]:
    return [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]


async def _history(session, household, member, category, amounts):
    for amount in amounts:
        await create_expense(
            session,
            household_id=household.id,
            member_id=member.id,
            category_id=category.id,
            amount=amount,
        )


async def _reach_confirmation(session, member, category, state, amount):
    await state.set_state(AddExpense.category)
    await state.update_data(amount=amount)
    callback = FakeCallback()
    await pick_category(
        callback,
        callback_data=CategoryCb(action="pick", category_id=category.id),
        state=state,
        session=session,
        member=member,
    )
    await skip_description(callback, state=state)
    return callback


async def test_confirmation_has_one_time_toggle(session, member, category, state):
    callback = await _reach_confirmation(session, member, category, state, 100)

    text, kwargs = callback.message.replies[-1]
    assert "Перевірте запис" in text
    assert labels(kwargs)[0] == "☐ Разова"


async def test_toggle_flips_flag_and_rerenders(session, member, category, state):
    callback = await _reach_confirmation(session, member, category, state, 100)
    toggle = FakeCallback()

    await toggle_one_time(toggle, state=state)

    assert (await state.get_data())["is_one_time"] is True
    assert labels(toggle.message.edits[-1][1])[0] == "☑ Разова"

    await toggle_one_time(toggle, state=state)
    assert (await state.get_data())["is_one_time"] is False


async def test_saving_a_one_time_expense(session, member, category, state):
    await _reach_confirmation(session, member, category, state, 100)
    await toggle_one_time(FakeCallback(), state=state)
    confirm = FakeCallback()

    await save_expense(confirm, state=state, session=session, member=member)

    saved = await list_expenses(session, member.household_id)
    assert saved[0].is_one_time is True
    assert "разова" in confirm.message.last_edit


async def test_anomalous_amount_warns_on_confirmation(session, household, member, category, state):
    await _history(session, household, member, category, [100, 100, 100, 100, 100])

    callback = await _reach_confirmation(session, member, category, state, 400)

    text = callback.message.last_reply
    assert "значно більша за типову для «Їжа» (звичайно ~100 ₴)" in text
    assert text.index("значно більша") < text.index("Перевірте запис")


async def test_no_anomaly_warning_with_too_little_history(
    session, household, member, category, state
):
    await _history(session, household, member, category, [100, 100, 100, 100])

    callback = await _reach_confirmation(session, member, category, state, 400)

    assert "значно більша" not in callback.message.last_reply


async def _month_limit(session, member, category, amount):
    await set_limit(
        session,
        household_id=member.household_id,
        member_id=member.id,
        period_type=Period.MONTH,
        category_id=category.id,
        amount=amount,
    )


async def _save(session, member, category, state, amount, one_time=False):
    await state.set_state(AddExpense.confirm)
    await state.update_data(
        amount=amount, category_id=category.id, category_name=category.name, is_one_time=one_time
    )
    confirm = FakeCallback()
    await save_expense(confirm, state=state, session=session, member=member)
    return confirm.message.last_edit


async def test_limit_alert_after_save(session, household, member, category, state):
    await _history(session, household, member, category, [700])
    await _month_limit(session, member, category, 1000)

    text = await _save(session, member, category, state, 150)

    assert "⚠️ Їжа (місяць): 850 ₴ / 1 000 ₴ — 85%" in text


async def test_no_limit_alert_below_threshold_or_for_one_time(
    session, household, member, category, state
):
    await _month_limit(session, member, category, 1000)

    assert "Їжа (місяць)" not in await _save(session, member, category, state, 100)
    assert "Їжа (місяць)" not in await _save(session, member, category, state, 5000, one_time=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_handlers_add_expense.py tests/test_formatting_limits.py tests/test_formatting.py -v`
Expected: FAIL — `ImportError: cannot import name 'toggle_one_time'` / `format_limit_alert`.

- [ ] **Step 3: Formatting**

In `src/budget_bot/formatting.py`, in `format_expense_line`, right after building `parts`:

```python
    if expense.is_one_time:
        parts.append("разова")
```

Append:

```python
def format_limit_alert(progress: LimitProgress) -> str:
    head = (
        f"{escape(progress.name)} ({LIMIT_PERIOD_TITLES[progress.period_type]}): "
        f"{format_amount(progress.spent)} / {format_amount(progress.amount)} — "
    )
    if progress.status is LimitStatus.OVER:
        over = progress.spent - progress.amount
        return f"🔴 {head}" + (f"перевищено на {format_amount(over)}" if over else "ліміт вичерпано")
    return f"⚠️ {head}{progress.percent}%"
```

- [ ] **Step 4: Keyboard**

Replace `confirm_keyboard` in `src/budget_bot/bot/keyboards.py`:

```python
def confirm_keyboard(is_one_time: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{'☑' if is_one_time else '☐'} Разова",
        callback_data=FlowCb(action="toggle_one_time"),
    )
    builder.button(text="✅ Зберегти", callback_data=FlowCb(action="save"))
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(1, 2)
    return builder.as_markup()
```

Update the comment on `FlowCb.action` in `src/budget_bot/bot/callbacks.py` to include `"toggle_one_time"`.

- [ ] **Step 5: Handler**

In `src/budget_bot/bot/handlers/add_expense.py`:
- update the module docstring to `"""/add: amount → category → optional description → confirmation (with one-time toggle)."""`;
- import `from budget_bot.clock import utcnow`, `format_limit_alert` (formatting), `is_anomalous`, `typical_amount` (services.expenses), `WARN_PERCENT`, `progress_for_expense` (services.limits).

In `pick_category`, replace the `update_data` line:

```python
    await state.update_data(
        category_id=category.id,
        category_name=category.name,
        typical=await typical_amount(session, member.household_id, category.id),
    )
```

Replace `_ask_confirmation` with:

```python
def _confirmation_text(data: dict) -> str:
    lines = []
    if is_anomalous(data["amount"], data.get("typical")):
        lines += [
            f"⚠️ Сума значно більша за типову для «{escape(data['category_name'])}» "
            f"(звичайно ~{format_amount(data['typical'])}). Все вірно? "
            "Якщо це одноразова подія — позначте її.",
            "",
        ]
    description = data.get("description")
    lines += [
        "Перевірте запис:",
        f"Сума: <b>{format_amount(data['amount'])}</b>",
        f"Категорія: {escape(data['category_name'])}",
        f"Опис: {escape(description) if description else '—'}",
    ]
    return "\n".join(lines)


async def _ask_confirmation(message: Message, state: FSMContext, description: str | None) -> None:
    data = await state.update_data(description=description, is_one_time=False)
    await state.set_state(AddExpense.confirm)
    await message.answer(_confirmation_text(data), reply_markup=confirm_keyboard())


@router.callback_query(AddExpense.confirm, FlowCb.filter(F.action == "toggle_one_time"))
async def toggle_one_time(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    data = await state.update_data(is_one_time=not data.get("is_one_time", False))
    await edit_or_answer(
        callback, _confirmation_text(data), reply_markup=confirm_keyboard(data["is_one_time"])
    )
    await callback.answer()
```

In `save_expense`, pass the flag and append alerts — replace the `create_expense(...)` call and the reply:

```python
    expense = await create_expense(
        session,
        household_id=member.household_id,
        member_id=member.id,
        category_id=data["category_id"],
        amount=data["amount"],
        description=data.get("description"),
        is_one_time=data.get("is_one_time", False),
    )
    alerts = [
        format_limit_alert(item)
        for item in await progress_for_expense(session, expense, utcnow())
        if item.percent >= WARN_PERCENT
    ]
    text = format_saved_expense(expense)
    if alerts:
        text += "\n\n" + "\n".join(alerts)
    await edit_or_answer(callback, text)
    await callback.answer()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_handlers_add_expense.py tests/test_formatting_limits.py tests/test_formatting.py -v`
Expected: PASS, including the pre-existing `/add` tests.

- [ ] **Step 7: Full suite, lint, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

```bash
git add src/budget_bot/bot/keyboards.py src/budget_bot/bot/callbacks.py src/budget_bot/formatting.py src/budget_bot/bot/handlers/add_expense.py tests/test_handlers_add_expense.py tests/test_formatting_limits.py tests/test_formatting.py
git commit -m "feat: one-time toggle, anomaly warning and limit alerts in /add

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `/list` — one-time marker and toggle on the expense card

**Files:**
- Modify: `src/budget_bot/formatting.py`, `src/budget_bot/bot/keyboards.py`, `src/budget_bot/bot/callbacks.py`, `src/budget_bot/bot/handlers/expense_list.py`
- Test: `tests/test_handlers_expense_list.py`

**Interfaces:**
- Consumes: `set_one_time` (Task 2); `format_expense_line` marker (Task 7).
- Produces: `expense_card_keyboard(expense_id: int, is_one_time: bool = False)`; `ExpenseCb` action `"toggle_one_time"`; handler `toggle_expense_one_time(callback, callback_data, session, member)`; card line `🔁 Разова витрата`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_handlers_expense_list.py` (extend the handler import with `toggle_expense_one_time`):

```python
def card_buttons(kwargs) -> list[str]:
    return [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]


async def test_card_offers_mark_as_one_time(session, household, member, category):
    expense = await make(session, household, member, category, 100)
    callback = FakeCallback()

    await show_expense(
        callback,
        callback_data=ExpenseCb(action="view", expense_id=expense.id),
        session=session,
        member=member,
    )

    assert "🔁 Позначити як разову" in card_buttons(callback.message.replies[-1][1])


async def test_toggle_marks_and_unmarks(session, household, member, partner, category):
    expense = await make(session, household, member, category, 100)
    callback = FakeCallback()
    data = ExpenseCb(action="toggle_one_time", expense_id=expense.id)

    await toggle_expense_one_time(callback, callback_data=data, session=session, member=partner)

    text, kwargs = callback.message.edits[-1]
    assert "🔁 Разова витрата" in text
    assert "↩️ Зняти позначку разової" in card_buttons(kwargs)
    assert expense.is_one_time is True and expense.updated_by_id == partner.id

    await toggle_expense_one_time(callback, callback_data=data, session=session, member=member)

    assert expense.is_one_time is False
    assert "🔁 Разова витрата" not in callback.message.last_edit


async def test_toggle_on_missing_expense(session, member, category):
    callback = FakeCallback()

    await toggle_expense_one_time(
        callback,
        callback_data=ExpenseCb(action="toggle_one_time", expense_id=9999),
        session=session,
        member=member,
    )

    assert callback.answers[-1][1] is True
    assert callback.message.edits == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_handlers_expense_list.py -v`
Expected: FAIL — `ImportError: cannot import name 'toggle_expense_one_time'`.

- [ ] **Step 3: Implement**

`src/budget_bot/bot/callbacks.py` — update the `ExpenseCb.action` comment to include `"toggle_one_time"`.

`src/budget_bot/formatting.py`, `format_expense_card` — after the description line:

```python
    if expense.is_one_time:
        lines.append("🔁 Разова витрата")
```

`src/budget_bot/bot/keyboards.py` — replace `expense_card_keyboard`:

```python
def expense_card_keyboard(expense_id: int, is_one_time: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Редагувати", callback_data=ExpenseCb(action="edit", expense_id=expense_id)
    )
    builder.button(
        text="🗑 Видалити", callback_data=ExpenseCb(action="delete", expense_id=expense_id)
    )
    builder.button(
        text="↩️ Зняти позначку разової" if is_one_time else "🔁 Позначити як разову",
        callback_data=ExpenseCb(action="toggle_one_time", expense_id=expense_id),
    )
    builder.adjust(2, 1)
    return builder.as_markup()
```

`src/budget_bot/bot/handlers/expense_list.py` — import `edit_or_answer` from `budget_bot.bot.replies` and `set_one_time` from services.expenses; in `show_expense` pass the flag:

```python
    await callback.message.answer(
        format_expense_card(expense),
        reply_markup=expense_card_keyboard(expense.id, expense.is_one_time),
    )
```

and append:

```python
@router.callback_query(ExpenseCb.filter(F.action == "toggle_one_time"))
async def toggle_expense_one_time(
    callback: CallbackQuery,
    callback_data: ExpenseCb,
    session: AsyncSession,
    member: Member,
) -> None:
    expense = await get_expense(session, member.household_id, callback_data.expense_id)
    if expense is None:
        await callback.answer(MISSING_EXPENSE_TEXT, show_alert=True)
        return

    expense = await set_one_time(
        session, expense, editor_id=member.id, value=not expense.is_one_time
    )
    await edit_or_answer(
        callback,
        format_expense_card(expense),
        reply_markup=expense_card_keyboard(expense.id, expense.is_one_time),
    )
    await callback.answer()
```

Update the module docstring to `"""/list: recent expenses plus the per-record card (with the one-time toggle)."""`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_handlers_expense_list.py tests/test_handlers_expense_delete.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite, lint, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`

```bash
git add src/budget_bot/formatting.py src/budget_bot/bot/keyboards.py src/budget_bot/bot/callbacks.py src/budget_bot/bot/handlers/expense_list.py tests/test_handlers_expense_list.py
git commit -m "feat: mark an expense as one-time from its card

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Docs and final verification

**Files:**
- Modify: `CLAUDE.md` (repo root)

**Interfaces:**
- Consumes: everything above. Produces: nothing new.

- [ ] **Step 1: Update `CLAUDE.md`**

In the `## Статус` section, append a paragraph:

```markdown
Phase 2 розбито на підпроєкти A–E (ліміти й разові витрати → заплановані платежі → MCP для
лімітів → дохід → проактивні сповіщення). Підпроєкт A реалізовано: `/setlimit`, `/limits`,
позначка «разова» (`/add`, картка `/list`), попередження про аномальну суму, ліміти й разові в
`/report`. Спек — `docs/superpowers/specs/2026-09-30-phase2-a-limits-one-time-design.md`.
Правило «бот не пише першим» можна переглянути, якщо воно блокує функціонал (підпроєкт E).
```

- [ ] **Step 2: Full verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`
Expected: all tests pass, no lint or format issues.

Run: `DATABASE_PATH=$(mktemp -d)/check.sqlite3 .venv/bin/alembic upgrade head && echo OK`
Expected: `OK` — fresh database migrates cleanly.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: record Phase 2 sub-project A status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Manual acceptance checklist (for the user after deploy)**

Не автоматизується — перевіряють двоє користувачів у Telegram після деплою на Railway:
1. `/setlimit` → Місяць → Загальний → 50000; `/limits` показує ліміт і прогноз.
2. `/add` з великою сумою в категорії з історією → попередження; позначити «Разова» → зберегти → у `/limits` прогрес не змінився, у `/report` є «з них разових».
3. Картка з `/list` → «Позначити як разову» / «Зняти позначку».
4. У `/limits` ✏️ змінює суму («було …»), 🗑 знімає ліміт.
