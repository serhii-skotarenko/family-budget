# Phase 2 · D — Income, Free Cashflow, «Зв'язок» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Зберігати місячний дохід сім'ї з історією змін, показувати вільний кешфлоу в місячному й річному `/report` і в MCP-конекторі, додати категорію «Зв'язок».

**Architecture:** Нова append-only таблиця `incomes` (як `limits`) і сервіс `services/income.py` з розрахунком доходу місяця (`as_of = min(now, кінець місяця − 1 мкс)`) і кешфлоу за цілі календарні місяці. Бот: діалог `/setincome`, рядки доходу/кешфлоу у `format_report`. Конектор: інструмент `get_cashflow` і поле `current_monthly_income` в огляді. «Зв'язок» — у `DEFAULT_CATEGORIES` і даними в тій самій міграції `0003`.

**Tech Stack:** Python 3.12, aiogram 3, SQLAlchemy 2 async + aiosqlite, Alembic, MCP SDK `mcp==2.2.0`, pytest + pytest-asyncio, ruff + black.

**Spec:** `docs/superpowers/specs/2026-09-30-phase2-d-income-design.md`; MCP-частина — розділ «`get_cashflow` (Phase 2 D)» у `docs/superpowers/specs/2026-09-15-claude-mcp-connector-design.md`.

## Global Constraints

- **Джерело правди — специфікація.** Якщо план і специфікація розійдуться — зупинитися й спитати.
- **Гілка:** `feat/phase2-income` (стоїть на `feat/phase2-connector-limits`). Усі команди — з каталогу `tg-bot/`: `.venv/bin/python -m pytest …`, `.venv/bin/ruff check src tests`, `.venv/bin/black --check src tests`.
- **Форматування:** перед кожним комітом `.venv/bin/black src tests alembic`. Якщо `ruff` скаржиться на E501 для довгого рядкового літерала — розбити його неявною конкатенацією, не змінюючи значення.
- **Суми** — цілі гривні, ввід доходу через `parse_amount` (1 … 10 000 000).
- **Час:** у БД — UTC-naive (`clock.utcnow`); місяці — календарні за Europe/Kyiv (`periods.kyiv_day_range`).
- **Дохід:** рядки `incomes` лише додаються; дохід місяця — остання версія з `effective_from ≤ min(now, кінець місяця − 1 мкс)`; місяць у майбутньому — без доходу.
- **Кешфлоу** = дохід − **усі** витрати (разом із разовими), лише за місяці, у яких дохід був. Поточний місяць — факт на зараз, без прогнозу.
- **Мінус** у від'ємному кешфлоу — символ U+2212 `−`.
- **«Зв'язок»** — апостроф U+0027 `'`, як у «Здоров'я»; `name_normalized = "зв'язок"`.
- **Конектор** — лише читання; логи без аргументів і даних; інструмент із `title` і `ToolAnnotations(read_only_hint=True, open_world_hint=False)`.
- **Мова:** код, докстрінги, commit-меседжі — англійською; тексти бота й prose у доках — українською. Conventional commits, кожен коміт закінчується рядком `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Тести:** реальна SQLite (фікстури `session`, `budget_db`, `budget_writer`, `readonly_session_factory`), очікувані числа пораховані вручну, без моків БД.

## Review Focus

1. **Сім'я без жодної категорії під час міграції `0003`** — «Зв'язок» не можна вставляти, інакше `ensure_default_categories` (сідить лише коли категорій 0) потім пропустить увесь базовий список (тест у Task 1).
2. **Дохід змінено вже після кінця місяця** — вересень рахується з вересневою версією, а не з жовтневою (тести в Task 2 і Task 5).
3. **Річний кешфлоу, коли дохід задано посеред року** — витрати місяців без доходу не входять (тест у Task 2), примітка «з <місяця>» (тест у Task 4).
4. **Від'ємний кешфлоу** — `−500 ₴ 🔴`, не `-500` і не `500` (тест у Task 4).
5. **`get_cashflow` з діапазоном у майбутньому** — порожній список, не помилка; понад 60 місяців — помилка з підказкою (тест у Task 5).

## File Structure

Шляхи — відносно `tg-bot/`, крім файлів у корені репозиторію (`CLAUDE.md`, `docs/`).

| Файл | Дія | Відповідальність | Задача |
|---|---|---|---|
| `src/budget_bot/models.py` | змінити | модель `Income` | 1 |
| `alembic/versions/0003_income_and_connectivity_category.py` | створити | таблиця `incomes` + дані «Зв'язок» | 1 |
| `src/budget_bot/services/categories.py` | змінити | «Зв'язок» у `DEFAULT_CATEGORIES` | 1 |
| `../docs/requirements.md` | змінити | базовий список категорій | 1 |
| `src/budget_bot/periods.py` | змінити | `MONTHS_UK_GENITIVE` | 2 |
| `src/budget_bot/services/income.py` | створити | історія доходу, кешфлоу | 2 |
| `src/budget_bot/formatting.py` | змінити | повідомлення `/setincome`; рядки кешфлоу у звіті | 3, 4 |
| `src/budget_bot/bot/handlers/income.py` | створити | `/setincome` | 3 |
| `src/budget_bot/bot/handlers/__init__.py`, `common.py`, `src/budget_bot/__main__.py` | змінити | роутер, довідка, меню | 3 |
| `src/budget_bot/bot/handlers/reports.py` | змінити | кешфлоу в `/report` | 4 |
| `src/budget_bot/connector/{schemas,analytics,tools}.py` | змінити | `get_cashflow`, поле в огляді | 5 |
| `tests/conftest.py` | змінити | `BudgetWriter.set_income` | 5 |
| `README.md`, `../CLAUDE.md` | змінити | документація | 6 |

---

### Task 1: Schema — `Income`, migration 0003, «Зв'язок»

**Files:**
- Modify: `src/budget_bot/models.py`, `src/budget_bot/services/categories.py`, `../docs/requirements.md`
- Create: `alembic/versions/0003_income_and_connectivity_category.py`
- Test: `tests/test_migrations.py`, `tests/test_models.py`, `tests/test_services_categories.py`, `tests/test_handlers_categories.py`, `tests/test_connector_summary.py`, `tests/conftest.py` (docstring only)

**Interfaces:**
- Produces: `budget_bot.models.Income` (`id`, `household_id`, `amount: int`, `effective_from`, `created_by_id`, `created_at`); `DEFAULT_CATEGORIES` with `"Зв'язок"` after `"Комунальні"` (10 names).

- [ ] **Step 1: Write the failing tests**

`tests/test_services_categories.py`: in `EXPECTED_DEFAULT_CATEGORIES` insert `"Зв'язок",` after `"Комунальні",`; rename `test_seeds_nine_default_categories_in_canonical_order` to `test_seeds_default_categories_in_canonical_order` and change both `== 9` in that file to `== 10`.

`tests/test_handlers_categories.py`: change `== 9` to `== 10`.

`tests/test_connector_summary.py`: in `DEFAULT_CATEGORY_NAMES` insert `"Зв'язок",` after `"Комунальні",`.

`tests/conftest.py`: in the `budget_db` docstring replace `the nine default categories` with `the default categories`.

Append to `tests/test_models.py` (add `Income` to the models import):

```python
async def test_income_persists(session, household, member):
    session.add(
        Income(
            household_id=household.id,
            amount=300000,
            effective_from=utcnow(),
            created_by_id=member.id,
        )
    )
    await session.commit()

    (row,) = list(await session.scalars(select(Income)))
    assert row.amount == 300000
    assert row.created_at is not None
```

Append to `tests/test_migrations.py`:

```python
def test_0003_adds_connectivity_only_where_missing_and_keeps_it_on_downgrade(tmp_path):
    db_path = tmp_path / "old.sqlite3"
    _alembic(db_path, "upgrade", "0002")
    connection = sqlite3.connect(db_path)
    with connection:
        for household_id in (1, 2, 3):
            connection.execute(
                "INSERT INTO households (id, name, created_at) VALUES (?, 'h', '2026-09-01')",
                (household_id,),
            )
        # 1: defaults without «Зв'язок»; 2: already has it (custom, other case);
        # 3: no categories at all yet.
        connection.execute(
            "INSERT INTO categories (household_id, name, name_normalized, is_custom, created_at) "
            "VALUES (1, 'Їжа', 'їжа', 0, '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO categories (household_id, name, name_normalized, is_custom, created_at) "
            "VALUES (2, 'ЗВ''ЯЗОК', 'зв''язок', 1, '2026-09-01')"
        )
    connection.close()

    _alembic(db_path, "upgrade", "head")
    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT household_id, name, name_normalized, is_custom FROM categories "
        "WHERE name_normalized = 'зв''язок' ORDER BY household_id"
    ).fetchall()
    connection.close()
    assert rows == [(1, "Зв'язок", "зв'язок", 0), (2, "ЗВ'ЯЗОК", "зв'язок", 1)]

    _alembic(db_path, "downgrade", "0002")
    connection = sqlite3.connect(db_path)
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master")]
    kept = connection.execute(
        "SELECT COUNT(*) FROM categories WHERE name = 'Зв''язок'"
    ).fetchone()
    connection.close()
    assert "incomes" not in tables
    assert kept == (1,)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py tests/test_migrations.py tests/test_services_categories.py tests/test_handlers_categories.py tests/test_connector_summary.py -q`
Expected: FAIL — `ImportError: cannot import name 'Income'`, and the category-count / category-list assertions.

- [ ] **Step 3: Model and default list**

Append to `src/budget_bot/models.py`:

```python
class Income(Base):
    """Monthly household income. Append-only: every change inserts a new row.

    The income of a month is the latest row with ``effective_from`` at or
    before the month's end (or now, for the current month).
    """

    __tablename__ = "incomes"
    __table_args__ = (Index("ix_incomes_lookup", "household_id", "effective_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    amount: Mapped[int]
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
```

In `src/budget_bot/services/categories.py` insert `"Зв'язок",` after `"Комунальні",` in `DEFAULT_CATEGORIES`, and change the `ensure_default_categories` docstring to `"""Seed the default categories, but only if the household has none yet."""`.

- [ ] **Step 4: Migration**

Create `alembic/versions/0003_income_and_connectivity_category.py`:

```python
"""income and the «Зв'язок» default category

Revision ID: 0003
Revises: 0002
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CONNECTIVITY = "Зв'язок"
CONNECTIVITY_NORMALIZED = "зв'язок"  # normalize_category_name(CONNECTIVITY)

categories = sa.table(
    "categories",
    sa.column("household_id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("name_normalized", sa.String),
    sa.column("is_custom", sa.Boolean),
    sa.column("created_at", sa.DateTime),
)


def upgrade() -> None:
    op.create_table(
        "incomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_incomes_lookup", "incomes", ["household_id", "effective_from"])

    # Only households that already have categories: one with none is seeded
    # later by ensure_default_categories, which skips any household that has
    # at least one category.
    connection = op.get_bind()
    with_categories = set(
        connection.execute(sa.select(categories.c.household_id).distinct()).scalars()
    )
    with_connectivity = set(
        connection.execute(
            sa.select(categories.c.household_id).where(
                categories.c.name_normalized == CONNECTIVITY_NORMALIZED
            )
        ).scalars()
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    for household_id in sorted(with_categories - with_connectivity):
        connection.execute(
            categories.insert().values(
                household_id=household_id,
                name=CONNECTIVITY,
                name_normalized=CONNECTIVITY_NORMALIZED,
                is_custom=False,
                created_at=now,
            )
        )


def downgrade() -> None:
    # «Зв'язок» stays: expenses may already point at it.
    op.drop_index("ix_incomes_lookup", table_name="incomes")
    op.drop_table("incomes")
```

- [ ] **Step 5: Requirements doc**

In `../docs/requirements.md` (repo root `docs/`), in both places that list the default categories, insert `Зв'язок` after `Комунальні`; in the «Базовий список категорій» decision line append `; додано "Зв'язок" 2026-09-30 (Phase 2 D)` before the closing `)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_models.py tests/test_migrations.py tests/test_services_categories.py tests/test_handlers_categories.py tests/test_connector_summary.py -q`
Expected: PASS, including `test_alembic_head_matches_models`.

- [ ] **Step 7: Full suite, lint, commit**

Run: `.venv/bin/black src tests alembic && .venv/bin/ruff check src tests alembic && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/models.py src/budget_bot/services/categories.py alembic/versions/0003_income_and_connectivity_category.py tests/test_models.py tests/test_migrations.py tests/test_services_categories.py tests/test_handlers_categories.py tests/test_connector_summary.py tests/conftest.py ../docs/requirements.md
git commit -m "feat: incomes table and the «Зв'язок» default category

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Income service

**Files:**
- Modify: `src/budget_bot/periods.py`
- Create: `src/budget_bot/services/income.py`
- Test: `tests/test_services_income.py`

**Interfaces:**
- Consumes: `Income` (Task 1); `Expense.is_one_time` (Phase 2 A); `periods.kyiv_day_range`, `to_kyiv`, `PeriodRange`.
- Produces:
  - `periods.MONTHS_UK_GENITIVE` (12 names: «січня» … «грудня»)
  - `services.income.month_first(day: date) -> date`, `next_month(first: date) -> date`, `month_range(first: date) -> PeriodRange`
  - `async set_income(session, *, household_id, member_id, amount, now: datetime | None = None) -> Income`
  - `async income_at(session, household_id, as_of: datetime) -> int | None`
  - `async month_income(session, household_id, first: date, now: datetime) -> int | None`
  - `@dataclass(frozen=True) MonthCashflow(first: date, income: int | None, spent: int, one_time: int, complete: bool)` + property `free -> int | None`
  - `async month_cashflow(session, household_id, first: date, now: datetime) -> MonthCashflow`
  - `@dataclass(frozen=True) Cashflow(income: int, spent: int, first_month: date, months: int)` + property `free -> int`
  - `async cashflow(session, household_id, first: date, last: date, now: datetime) -> Cashflow | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_services_income.py`:

```python
from datetime import date

from budget_bot.services.expenses import create_expense
from budget_bot.services.income import (
    cashflow,
    income_at,
    month_cashflow,
    month_income,
    month_range,
    next_month,
    set_income,
)
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)


async def income(session, household, member, amount, at):
    await set_income(
        session, household_id=household.id, member_id=member.id, amount=amount, now=at
    )


async def spend(session, household, member, category, amount, at, one_time=False):
    await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=amount,
        is_one_time=one_time,
        created_at=at,
    )


def test_month_helpers():
    assert next_month(date(2026, 12, 1)) == date(2027, 1, 1)
    bounds = month_range(date(2026, 10, 1))
    assert (bounds.start, bounds.end) == (kyiv(2026, 10, 1, 0), kyiv(2026, 11, 1, 0))


async def test_no_income_yet(session, household):
    assert await income_at(session, household.id, NOW) is None
    assert await cashflow(session, household.id, date(2026, 1, 1), date(2026, 10, 1), NOW) is None


async def test_month_income_follows_history(session, household, member):
    await income(session, household, member, 300000, kyiv(2026, 9, 5))
    await income(session, household, member, 312000, kyiv(2026, 10, 20))  # after NOW

    # August: nothing yet. September: the version in force at its end.
    assert await month_income(session, household.id, date(2026, 8, 1), NOW) is None
    assert await month_income(session, household.id, date(2026, 9, 1), NOW) == 300000
    # October is current: a version from the future (20.10 > NOW) does not count yet.
    assert await month_income(session, household.id, date(2026, 10, 1), NOW) == 300000
    # November has not started.
    assert await month_income(session, household.id, date(2026, 11, 1), NOW) is None


async def test_change_mid_month_applies_to_the_whole_month(session, household, member):
    await income(session, household, member, 300000, kyiv(2026, 9, 5))
    await income(session, household, member, 312000, kyiv(2026, 10, 2))

    assert await month_income(session, household.id, date(2026, 9, 1), NOW) == 300000
    assert await month_income(session, household.id, date(2026, 10, 1), NOW) == 312000


async def test_month_cashflow_counts_all_expenses(session, household, member, category):
    await income(session, household, member, 300000, kyiv(2026, 9, 5))
    await spend(session, household, member, category, 2000, kyiv(2026, 9, 1, 0, 5))
    await spend(session, household, member, category, 500, kyiv(2026, 9, 30, 23, 50), True)
    await spend(session, household, member, category, 9999, kyiv(2026, 10, 1, 0, 1))

    september = await month_cashflow(session, household.id, date(2026, 9, 1), NOW)

    assert (september.income, september.spent, september.one_time) == (300000, 2500, 500)
    assert (september.free, september.complete) == (297500, True)
    october = await month_cashflow(session, household.id, date(2026, 10, 1), NOW)
    assert (october.spent, october.complete) == (9999, False)


async def test_year_cashflow_uses_only_months_with_income(session, household, member, category):
    await income(session, household, member, 300000, kyiv(2026, 9, 5))
    await income(session, household, member, 312000, kyiv(2026, 10, 2))
    await spend(session, household, member, category, 1000, kyiv(2026, 8, 10))  # no income yet
    await spend(session, household, member, category, 1500, kyiv(2026, 9, 10))
    await spend(session, household, member, category, 500, kyiv(2026, 9, 11), True)
    await spend(session, household, member, category, 3000, kyiv(2026, 10, 3))

    result = await cashflow(session, household.id, date(2026, 1, 1), date(2026, 12, 1), NOW)

    assert (result.first_month, result.months) == (date(2026, 9, 1), 2)
    assert (result.income, result.spent, result.free) == (612000, 5000, 607000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_services_income.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.services.income'`.

- [ ] **Step 3: Genitive month names**

In `src/budget_bot/periods.py`, after `MONTHS_UK`:

```python
# "з жовтня", "діє з вересня 2026"
MONTHS_UK_GENITIVE = (
    "січня",
    "лютого",
    "березня",
    "квітня",
    "травня",
    "червня",
    "липня",
    "серпня",
    "вересня",
    "жовтня",
    "листопада",
    "грудня",
)
```

- [ ] **Step 4: The service**

Create `src/budget_bot/services/income.py`:

```python
"""Monthly household income: append-only history and free cashflow for whole months.

A month uses the income in force at its last moment, or now for the current
month; free cashflow is that income minus all of the month's expenses,
one-time ones included.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.clock import utcnow
from budget_bot.models import Expense, Income
from budget_bot.periods import PeriodRange, kyiv_day_range, to_kyiv


def month_first(day: date) -> date:
    return day.replace(day=1)


def next_month(first: date) -> date:
    return (first + timedelta(days=32)).replace(day=1)


def month_range(first: date) -> PeriodRange:
    return kyiv_day_range(first, next_month(first) - timedelta(days=1))


async def set_income(
    session: AsyncSession,
    *,
    household_id: int,
    member_id: int,
    amount: int,
    now: datetime | None = None,
) -> Income:
    now = now or utcnow()
    row = Income(
        household_id=household_id,
        amount=amount,
        effective_from=now,
        created_by_id=member_id,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def income_at(session: AsyncSession, household_id: int, as_of: datetime) -> int | None:
    return await session.scalar(
        select(Income.amount)
        .where(Income.household_id == household_id, Income.effective_from <= as_of)
        .order_by(Income.effective_from.desc(), Income.id.desc())
        .limit(1)
    )


async def month_income(
    session: AsyncSession, household_id: int, first: date, now: datetime
) -> int | None:
    bounds = month_range(first)
    if bounds.start > now:
        return None
    as_of = min(now, bounds.end - timedelta(microseconds=1))
    return await income_at(session, household_id, as_of)


@dataclass(frozen=True)
class MonthCashflow:
    first: date
    income: int | None
    spent: int  # all expenses of the month, one-time included
    one_time: int
    complete: bool

    @property
    def free(self) -> int | None:
        return None if self.income is None else self.income - self.spent


async def month_cashflow(
    session: AsyncSession, household_id: int, first: date, now: datetime
) -> MonthCashflow:
    bounds = month_range(first)
    spent, one_time = (
        await session.execute(
            select(
                func.coalesce(func.sum(Expense.amount), 0),
                func.coalesce(func.sum(case((Expense.is_one_time, Expense.amount), else_=0)), 0),
            ).where(
                Expense.household_id == household_id,
                Expense.created_at >= bounds.start,
                Expense.created_at < bounds.end,
            )
        )
    ).one()
    return MonthCashflow(
        first=first,
        income=await month_income(session, household_id, first, now),
        spent=int(spent),
        one_time=int(one_time),
        complete=now >= bounds.end,
    )


@dataclass(frozen=True)
class Cashflow:
    income: int
    spent: int
    first_month: date  # the first month whose income is counted
    months: int  # how many months had an income

    @property
    def free(self) -> int:
        return self.income - self.spent


async def cashflow(
    session: AsyncSession, household_id: int, first: date, last: date, now: datetime
) -> Cashflow | None:
    """Cashflow over the calendar months first..last (month starts), up to the current one.

    Only months with an income count, and only their expenses: spending from
    months before the income was set would otherwise skew the result.
    """
    current = month_first(to_kyiv(now).date())
    counted = []
    month = first
    while month <= last and month <= current:
        item = await month_cashflow(session, household_id, month, now)
        if item.income is not None:
            counted.append(item)
        month = next_month(month)
    if not counted:
        return None
    return Cashflow(
        income=sum(item.income for item in counted),
        spent=sum(item.spent for item in counted),
        first_month=counted[0].first,
        months=len(counted),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_services_income.py -q`
Expected: PASS.

- [ ] **Step 6: Full suite, lint, commit**

Run: `.venv/bin/black src tests && .venv/bin/ruff check src tests && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/periods.py src/budget_bot/services/income.py tests/test_services_income.py
git commit -m "feat: income service with monthly history and cashflow

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `/setincome`

**Files:**
- Modify: `src/budget_bot/formatting.py`, `src/budget_bot/bot/handlers/__init__.py`, `src/budget_bot/bot/handlers/common.py`, `src/budget_bot/__main__.py`
- Create: `src/budget_bot/bot/handlers/income.py`
- Test: `tests/test_handlers_income.py`, `tests/test_handlers_common.py`

**Interfaces:**
- Consumes: `set_income`, `income_at` (Task 2); `periods.MONTHS_UK_GENITIVE`.
- Produces: `formatting.format_income_saved(amount: int, previous: int | None, now: datetime) -> str`; handlers `SetIncome` (state `amount`), `cmd_setincome(message, state, session, member)`, `enter_income(message, state, session, member)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handlers_income.py`:

```python
from budget_bot.bot.handlers.income import SetIncome, cmd_setincome, enter_income
from budget_bot.clock import utcnow
from budget_bot.services.income import income_at, set_income
from tests.conftest import FakeMessage


async def test_first_income(session, member, state):
    prompt = FakeMessage(text="/setincome")
    await cmd_setincome(prompt, state=state, session=session, member=member)

    assert await state.get_state() == SetIncome.amount
    assert "зараз" not in prompt.last_reply

    reply = FakeMessage(text="300 000")
    await enter_income(reply, state=state, session=session, member=member)

    assert await state.get_state() is None
    assert await income_at(session, member.household_id, utcnow()) == 300000
    assert reply.last_reply.startswith("✅ Дохід: <b>300 000 ₴</b>/міс, діє з ")


async def test_changing_income_shows_the_previous_one(session, member, state):
    await set_income(session, household_id=member.household_id, member_id=member.id, amount=300000)
    prompt = FakeMessage(text="/setincome")
    await cmd_setincome(prompt, state=state, session=session, member=member)

    assert "(зараз: 300 000 ₴)" in prompt.last_reply

    reply = FakeMessage(text="312000")
    await enter_income(reply, state=state, session=session, member=member)

    assert "/міс (було 300 000 ₴), діє з " in reply.last_reply
    assert await income_at(session, member.household_id, utcnow()) == 312000


async def test_invalid_amount_keeps_the_step(session, member, state):
    await state.set_state(SetIncome.amount)
    message = FakeMessage(text="0")

    await enter_income(message, state=state, session=session, member=member)

    assert await state.get_state() == SetIncome.amount
    assert "більшою за нуль" in message.last_reply
    assert await income_at(session, member.household_id, utcnow()) is None
```

Append to `tests/test_formatting.py` (add `format_income_saved` to its formatting import):

```python
def test_income_saved_names_the_month_in_genitive():
    text = format_income_saved(312000, 300000, kyiv(2026, 10, 15))

    assert text == (
        "✅ Дохід: <b>312 000 ₴</b>/міс (було 300 000 ₴), діє з жовтня 2026"
    )
```

Append to `tests/test_handlers_common.py`:

```python
def test_help_and_command_menu_list_setincome():
    from budget_bot.__main__ import BOT_COMMANDS
    from budget_bot.bot.handlers.common import HELP_TEXT

    assert "/setincome" in HELP_TEXT
    assert "setincome" in {command.command for command in BOT_COMMANDS}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_handlers_income.py tests/test_formatting.py tests/test_handlers_common.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'budget_bot.bot.handlers.income'`.

- [ ] **Step 3: Formatter**

In `src/budget_bot/formatting.py` add `MONTHS_UK_GENITIVE` to the `budget_bot.periods` import, `from datetime import datetime, timedelta` (merge with the existing `timedelta` import), and append:

```python
def format_income_saved(amount: int, previous: int | None, now: datetime) -> str:
    text = f"✅ Дохід: <b>{format_amount(amount)}</b>/міс"
    if previous is not None:
        text += f" (було {format_amount(previous)})"
    local = to_kyiv(now)
    return f"{text}, діє з {MONTHS_UK_GENITIVE[local.month - 1]} {local.year}"
```

- [ ] **Step 4: Handler**

Create `src/budget_bot/bot/handlers/income.py`:

```python
"""/setincome: the household's monthly income, one step."""

from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.amounts import AmountError, format_amount, parse_amount
from budget_bot.bot.keyboards import cancel_keyboard
from budget_bot.bot.predicates import NOT_A_COMMAND
from budget_bot.clock import utcnow
from budget_bot.formatting import format_income_saved
from budget_bot.models import Member
from budget_bot.services.income import income_at, set_income

router = Router(name="income")


class SetIncome(StatesGroup):
    amount = State()


@router.message(Command("setincome"))
async def cmd_setincome(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    await state.set_state(SetIncome.amount)
    await state.set_data({})
    current = await income_at(session, member.household_id, utcnow())
    hint = f" (зараз: {format_amount(current)})" if current is not None else ""
    await message.answer(
        f"💰 Введіть місячний дохід сім'ї в гривнях{hint}:", reply_markup=cancel_keyboard()
    )


@router.message(SetIncome.amount, NOT_A_COMMAND)
async def enter_income(
    message: Message, state: FSMContext, session: AsyncSession, member: Member
) -> None:
    try:
        amount = parse_amount(message.text or "")
    except AmountError as error:
        await message.answer(f"⚠️ {escape(str(error))}", reply_markup=cancel_keyboard())
        return

    now = utcnow()
    previous = await income_at(session, member.household_id, now)
    await state.clear()
    await set_income(
        session, household_id=member.household_id, member_id=member.id, amount=amount, now=now
    )
    await message.answer(format_income_saved(amount, previous, now))
```

Register it: in `src/budget_bot/bot/handlers/__init__.py` add `income` to the import list and `income.router,` right after `limits.router,`.

In `src/budget_bot/bot/handlers/common.py`, `HELP_TEXT`, after the `/setlimit` line add:

```python
    "💰 /setincome — місячний дохід сім'ї (для кешфлоу у звіті)\n"
```

In `src/budget_bot/__main__.py`, `BOT_COMMANDS`, after `setlimit`:

```python
    BotCommand(command="setincome", description="Місячний дохід"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_handlers_income.py tests/test_formatting.py tests/test_handlers_common.py tests/test_dispatch_smoke.py -q`
Expected: PASS.

- [ ] **Step 6: Full suite, lint, commit**

Run: `.venv/bin/black src tests && .venv/bin/ruff check src tests && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/formatting.py src/budget_bot/bot/handlers/income.py src/budget_bot/bot/handlers/__init__.py src/budget_bot/bot/handlers/common.py src/budget_bot/__main__.py tests/test_handlers_income.py tests/test_formatting.py tests/test_handlers_common.py
git commit -m "feat: /setincome dialog

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Income and free cashflow in `/report`

**Files:**
- Modify: `src/budget_bot/formatting.py`, `src/budget_bot/bot/handlers/reports.py`
- Test: `tests/test_formatting.py`, `tests/test_handlers_reports.py`

**Interfaces:**
- Consumes: `Cashflow`, `cashflow`, `month_first` (Task 2); `MONTHS_UK_GENITIVE`.
- Produces: `format_report(report, limits=(), cashflow: Cashflow | None = None, note_income_start: bool = False) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_formatting.py` (add `from budget_bot.services.income import Cashflow`; `date` from `datetime` if missing):

```python
def _month_report(total):
    return Report(
        period_label="поточний місяць (жовтень 2026)",
        total=total,
        by_category=[CategoryTotal("Їжа", total, 100.0, category_id=1)],
        by_member=[MemberTotal("Сергій", total)],
    )


def test_report_shows_income_and_free_cashflow():
    cash = Cashflow(income=300000, spent=58400, first_month=date(2026, 10, 1), months=1)

    text = format_report(_month_report(58400), cashflow=cash)

    assert "Дохід: 300 000 ₴\nВільний кешфлоу: 241 600 ₴" in text
    assert text.index("Разом") < text.index("Дохід") < text.index("За категоріями")


def test_negative_cashflow_is_marked():
    cash = Cashflow(income=100, spent=600, first_month=date(2026, 10, 1), months=1)

    text = format_report(_month_report(600), cashflow=cash)

    assert "Вільний кешфлоу: −500 ₴ 🔴" in text


def test_year_report_notes_when_income_starts():
    cash = Cashflow(income=612000, spent=5000, first_month=date(2026, 9, 1), months=2)

    noted = format_report(_month_report(5000), cashflow=cash, note_income_start=True)
    january = Cashflow(income=10, spent=5, first_month=date(2026, 1, 1), months=10)
    plain = format_report(_month_report(5), cashflow=january, note_income_start=True)

    assert "(дохід враховано з вересня)" in noted
    assert "враховано" not in plain


def test_report_without_income_has_no_cashflow_lines():
    assert "Дохід" not in format_report(_month_report(100))
```

Append to `tests/test_handlers_reports.py` (add `from budget_bot.services.income import set_income`):

```python
async def test_month_report_with_income(session, household, member, category):
    await make(session, household, member, category, 600)
    await set_income(session, household_id=household.id, member_id=member.id, amount=300000)
    callback = FakeCallback()

    await cb_report(
        callback, callback_data=ReportCb(period="month"), session=session, member=member
    )

    text = callback.message.last_edit
    assert "Дохід: 300 000 ₴" in text
    assert "Вільний кешфлоу: 299 400 ₴" in text


async def test_year_report_with_income(session, household, member, category):
    await make(session, household, member, category, 600)
    await set_income(session, household_id=household.id, member_id=member.id, amount=300000)
    callback = FakeCallback()

    await cb_report(callback, callback_data=ReportCb(period="year"), session=session, member=member)

    assert "Вільний кешфлоу: 299 400 ₴" in callback.message.last_edit


async def test_week_report_has_no_income(session, household, member, category):
    await make(session, household, member, category, 600)
    await set_income(session, household_id=household.id, member_id=member.id, amount=300000)
    callback = FakeCallback()

    await cb_report(callback, callback_data=ReportCb(period="week"), session=session, member=member)

    assert "Дохід" not in callback.message.last_edit
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_formatting.py tests/test_handlers_reports.py -q`
Expected: FAIL — `TypeError: format_report() got an unexpected keyword argument 'cashflow'` and missing «Дохід» in the handler output.

- [ ] **Step 3: Formatter**

In `src/budget_bot/formatting.py` import `from budget_bot.services.income import Cashflow` and add above `format_report`:

```python
def _cashflow_lines(cash: Cashflow, note_income_start: bool) -> list[str]:
    free = cash.free
    free_text = format_amount(free) if free >= 0 else f"−{format_amount(-free)} 🔴"
    lines = [f"Дохід: {format_amount(cash.income)}", f"Вільний кешфлоу: {free_text}"]
    if note_income_start and cash.first_month.month != 1:
        lines.append(f"(дохід враховано з {MONTHS_UK_GENITIVE[cash.first_month.month - 1]})")
    return lines
```

Change the `format_report` signature and insert the lines right after the general-limit line:

```python
def format_report(
    report: Report,
    limits: Sequence[LimitProgress] = (),
    cashflow: Cashflow | None = None,
    note_income_start: bool = False,
) -> str:
```

```python
    if None in limit_by_category:
        lines.append(_limit_usage_line(limit_by_category[None]))
    if cashflow is not None:
        lines.extend(_cashflow_lines(cashflow, note_income_start))
```

- [ ] **Step 4: Handler**

In `src/budget_bot/bot/handlers/reports.py` import `from datetime import date`, `to_kyiv` from `budget_bot.periods`, and `from budget_bot.services.income import cashflow, month_first`. Replace the tail of `cb_report` (from `limits = (` to the end) with:

```python
    limits = (
        await limit_progress(session, member.household_id, report_period, now)
        if report_period in LIMIT_PERIODS
        else []
    )
    this_month = month_first(to_kyiv(now).date())
    if report_period is Period.MONTH:
        cash = await cashflow(session, member.household_id, this_month, this_month, now)
    elif report_period is Period.YEAR:
        january = date(this_month.year, 1, 1)
        cash = await cashflow(session, member.household_id, january, this_month, now)
    else:
        cash = None
    await edit_or_answer(
        callback,
        format_report(report, limits, cash, note_income_start=report_period is Period.YEAR),
    )
    await callback.answer()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_formatting.py tests/test_handlers_reports.py -q`
Expected: PASS.

- [ ] **Step 6: Full suite, lint, commit**

Run: `.venv/bin/black src tests && .venv/bin/ruff check src tests && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/formatting.py src/budget_bot/bot/handlers/reports.py tests/test_formatting.py tests/test_handlers_reports.py
git commit -m "feat: income and free cashflow in monthly and yearly /report

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Connector — `get_cashflow`, income in the overview

**Files:**
- Modify: `src/budget_bot/connector/schemas.py`, `src/budget_bot/connector/analytics.py`, `src/budget_bot/connector/tools.py`, `tests/conftest.py`
- Create: `tests/test_connector_cashflow.py`
- Test: `tests/test_connector_tools.py`

**Interfaces:**
- Consumes: `income_at`, `month_cashflow`, `month_first`, `month_range`, `next_month` (Task 2); `DateRange`, `InvalidRequest`, `MAX_TREND_BUCKETS` (connector inputs); fixture `september_one_time` (Phase 2 C).
- Produces: schemas `CashflowMonth`, `CashflowReport`; `BudgetOverview.current_monthly_income: int | None = None`; `analytics.cashflow_report(session, date_range, *, now_utc) -> CashflowReport`; MCP tool `get_cashflow(start_date, end_date)`; `BudgetWriter.set_income(*, amount: int, at: datetime)`.

- [ ] **Step 1: Test writer**

In `tests/conftest.py` import `from budget_bot.services.income import set_income` and add to `BudgetWriter`:

```python
    async def set_income(self, *, amount: int, at: datetime) -> None:
        async with self._factory() as db_session:
            member_id = await db_session.scalar(
                select(Member.id).where(Member.display_name == "Сергій")
            )
            await set_income(
                db_session,
                household_id=SINGLETON_HOUSEHOLD_ID,
                member_id=member_id,
                amount=amount,
                now=at,
            )
            await db_session.commit()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_connector_cashflow.py`:

```python
from datetime import date

import pytest
import pytest_asyncio

from budget_bot.connector.analytics import budget_overview, cashflow_report
from budget_bot.connector.inputs import DateRange, InvalidRequest
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)


@pytest_asyncio.fixture
async def incomes(september_one_time, budget_writer) -> None:
    """300 000 from 05.09, 312 000 from 02.10; one October expense of 3 000."""
    await budget_writer.set_income(amount=300000, at=kyiv(2026, 9, 5))
    await budget_writer.set_income(amount=312000, at=kyiv(2026, 10, 2))
    await budget_writer.add_expense(
        category="Їжа", member="Оля", amount=3000, at=kyiv(2026, 10, 3)
    )


async def report(session_factory, first, last):
    async with session_factory() as session:
        return await cashflow_report(session, DateRange(first, last), now_utc=NOW)


async def test_whole_months_with_income_from_when_it_was_set(incomes, readonly_session_factory):
    result = await report(readonly_session_factory, date(2026, 8, 10), date(2026, 12, 31))

    assert [month.model_dump() for month in result.months] == [
        {
            "month_start": date(2026, 8, 1),
            "month_end": date(2026, 8, 31),
            "income": None,
            "spent": 350,
            "one_time_amount": 0,
            "free_cashflow": None,
            "complete": True,
        },
        {
            # 250 + 100 + 1200 + 600 regular, 5000 + 300 one-time.
            "month_start": date(2026, 9, 1),
            "month_end": date(2026, 9, 30),
            "income": 300000,
            "spent": 7450,
            "one_time_amount": 5300,
            "free_cashflow": 292550,
            "complete": True,
        },
        {
            "month_start": date(2026, 10, 1),
            "month_end": date(2026, 10, 31),
            "income": 312000,
            "spent": 3000,
            "one_time_amount": 0,
            "free_cashflow": 309000,
            "complete": False,
        },
    ]


async def test_range_in_the_future_is_empty(incomes, readonly_session_factory):
    result = await report(readonly_session_factory, date(2026, 11, 1), date(2026, 12, 31))

    assert result.months == []


async def test_too_many_months_is_rejected(readonly_session_factory):
    with pytest.raises(InvalidRequest, match="max 60"):
        await report(readonly_session_factory, date(2020, 1, 1), date(2026, 10, 1))


async def test_overview_carries_the_current_income(incomes, readonly_session_factory):
    async with readonly_session_factory() as session:
        now_income = await budget_overview(session, now_utc=NOW)
        before = await budget_overview(session, now_utc=kyiv(2026, 9, 1))

    assert now_income.current_monthly_income == 312000
    assert before.current_monthly_income is None
```

In `tests/test_connector_tools.py`: add `"get_cashflow"` to the tool-name set in `test_every_tool_is_titled_and_read_only`, and append:

```python
async def test_get_cashflow_through_the_client(early_september, budget_writer, readonly_session_factory):
    await budget_writer.set_income(amount=300000, at=kyiv(2026, 9, 5))

    result = await call(
        readonly_session_factory,
        "get_cashflow",
        {"start_date": "2026-09-01", "end_date": "2026-09-30"},
    )

    assert result.is_error is False
    (september,) = result.structured_content["months"]
    # 250 + 100 + 1200 + 600 in September.
    assert (september["income"], september["spent"], september["free_cashflow"]) == (
        300000,
        2150,
        297850,
    )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_connector_cashflow.py tests/test_connector_tools.py -q`
Expected: FAIL — `ImportError: cannot import name 'cashflow_report'`.

- [ ] **Step 4: Schemas**

In `src/budget_bot/connector/schemas.py`, `BudgetOverview` gains a last field:

```python
    current_monthly_income: int | None = Field(
        None, description="Monthly household income in force now, UAH; null if never set"
    )
```

Append:

```python
class CashflowMonth(BaseModel):
    month_start: dt.date
    month_end: dt.date
    income: int | None = Field(description="Income in force in this month, UAH; null if not set")
    spent: int = Field(description="All expenses of the month, one-time included")
    one_time_amount: int = Field(description=ONE_TIME_AMOUNT)
    free_cashflow: int | None = Field(description="income - spent; null without an income")
    complete: bool = Field(description="True when the month has already ended")


class CashflowReport(BaseModel):
    start_date: dt.date
    end_date: dt.date
    months: list[CashflowMonth] = Field(
        description="Whole calendar months (Kyiv) overlapping the range, up to the current one"
    )
```

- [ ] **Step 5: Analytics**

In `src/budget_bot/connector/analytics.py` import `CashflowMonth`, `CashflowReport` (schemas) and `from budget_bot.services.income import income_at, month_cashflow, month_first, month_range, next_month`. In `budget_overview`, add to the `BudgetOverview(...)` call:

```python
        current_monthly_income=await income_at(session, HOUSEHOLD_ID, now_utc),
```

Append:

```python
async def cashflow_report(
    session: AsyncSession, date_range: DateRange, *, now_utc: datetime
) -> CashflowReport:
    """Income and free cashflow per whole calendar month overlapping the range."""
    first = month_first(date_range.first)
    last = min(month_first(date_range.last), month_first(to_kyiv(now_utc).date()))
    count = (last.year - first.year) * 12 + last.month - first.month + 1
    if count > MAX_TREND_BUCKETS:
        raise InvalidRequest(
            f"{date_range.first.isoformat()}..{date_range.last.isoformat()} gives {count} "
            f"months (max {MAX_TREND_BUCKETS}); use a shorter date range"
        )

    months = []
    month = first
    while month <= last:
        item = await month_cashflow(session, HOUSEHOLD_ID, month, now_utc)
        bounds = month_range(month)
        months.append(
            CashflowMonth(
                month_start=month,
                month_end=to_kyiv(bounds.end).date() - timedelta(days=1),
                income=item.income,
                spent=item.spent,
                one_time_amount=item.one_time,
                free_cashflow=item.free,
                complete=item.complete,
            )
        )
        month = next_month(month)
    return CashflowReport(start_date=date_range.first, end_date=date_range.last, months=months)
```

- [ ] **Step 6: The tool**

In `src/budget_bot/connector/tools.py` import `CashflowReport`; in `OVERVIEW_DESCRIPTION` replace `"and the number of expenses. Expense dates"` with `"the number of expenses and the monthly household income in force now (null if never set). Expense dates"` (keep the string split across lines as black leaves it). Add after `LIMITS_DESCRIPTION`:

```python
CASHFLOW_DESCRIPTION = (
    "Returns, for each whole calendar month (Kyiv time) overlapping an inclusive date range, "
    "up to the current month: the monthly household income set in the bot (null before it "
    "was first set), all spending in whole UAH including expenses marked one-time, the "
    "one-time part, free cashflow (income minus spending, null without an income) and "
    "whether the month has ended. At most 60 months per call."
)
```

Register after `get_limit_progress`:

```python
    @server.tool(
        name="get_cashflow",
        title="Дохід і кешфлоу",
        description=CASHFLOW_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def get_cashflow(
        ctx: Context, start_date: StartDate, end_date: EndDate
    ) -> CashflowReport:
        async def work(session: AsyncSession) -> CashflowReport:
            date_range = parse_date_range(start_date, end_date)
            return await analytics.cashflow_report(session, date_range, now_utc=utcnow())

        return await _run("get_cashflow", ctx, session_factory, work)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_connector_cashflow.py tests/test_connector_tools.py tests/test_connector_summary.py -q`
Expected: PASS.

- [ ] **Step 8: Full suite, lint, commit**

Run: `.venv/bin/black src tests && .venv/bin/ruff check src tests && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/connector/schemas.py src/budget_bot/connector/analytics.py src/budget_bot/connector/tools.py tests/conftest.py tests/test_connector_cashflow.py tests/test_connector_tools.py
git commit -m "feat(connector): get_cashflow tool and current income in the overview

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Docs and final verification

**Files:**
- Modify: `README.md` (in `tg-bot/`), `../CLAUDE.md`

- [ ] **Step 1: README**

In `tg-bot/README.md`, section «Claude-конектор», replace `п'ять інструментів — огляд бюджету, підсумок за період, динаміку по тижнях чи
місяцях, список записів і прогрес лімітів` with `шість інструментів — огляд бюджету, підсумок за період, динаміку по тижнях чи
місяцях, список записів, прогрес лімітів і дохід з вільним кешфлоу по місяцях` (keep the rest of the paragraph).

- [ ] **Step 2: CLAUDE.md**

In `CLAUDE.md`, section «Статус», replace `Підпроєкти A і C реалізовано.` with `Підпроєкти A, C і D реалізовано. D: `/setincome` (дохід з історією змін), дохід і вільний кешфлоу в місячному й річному `/report` і в конекторі (`get_cashflow`), категорія «Зв'язок».`

- [ ] **Step 3: Full verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests alembic && .venv/bin/black --check src tests alembic`
Expected: all green.

Run: `D=$(mktemp -d) && DATABASE_PATH=$D/check.sqlite3 .venv/bin/alembic upgrade head && echo OK && rm -rf $D`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add README.md ../CLAUDE.md
git commit -m "docs: income, cashflow and the connectivity category

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Manual check after deploy (for the user)**

1. У логах Railway: `Running upgrade 0002 -> 0003`.
2. `/categories` — є «Зв'язок».
3. `/setincome` → 300000; `/report` → Місяць — рядки «Дохід» і «Вільний кешфлоу»; Рік — те саме з приміткою «(дохід враховано з …)».
4. У claude.ai: «Скільки в нас лишилось вільних грошей у вересні?» — відповідає через `get_cashflow`.
