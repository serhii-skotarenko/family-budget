# Phase 2 · C — Connector: Limits and One-Time Expenses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дати Claude через MCP-конектор прогрес лімітів (поточний і минулі періоди) і розрізнення разових витрат у наявних інструментах.

**Architecture:** Лише пакет `budget_bot.connector`: новий аргумент `one_time` іде в спільні SQL-умови `_conditions`, нові поля — у Pydantic-схеми; п'ятий інструмент `get_limit_progress` обчислює прогрес через наявний `services.limits.limit_progress` з моментом оцінки `as_of = min(now, кінець періоду − 1 мкс)`. Схема БД і бот не змінюються.

**Tech Stack:** Python 3.12, MCP Python SDK `mcp==2.2.0`, SQLAlchemy 2 async + aiosqlite (read-only engine), pydantic 2, pytest + pytest-asyncio, ruff + black.

**Spec:** `docs/superpowers/specs/2026-09-15-claude-mcp-connector-design.md` (розділи з позначкою «Phase 2 C»); контекст лімітів — `docs/superpowers/specs/2026-09-30-phase2-a-limits-one-time-design.md`.

## Global Constraints

- **Джерело правди — специфікація.** Якщо план і специфікація розійдуться — зупинитися й спитати.
- **Гілка:** `feat/phase2-connector-limits`. Усі команди — з каталогу `tg-bot/`: `.venv/bin/python -m pytest …`, `.venv/bin/ruff check src tests`, `.venv/bin/black --check src tests`.
- **Форматування:** перед кожним комітом `.venv/bin/black src tests`. Якщо `ruff` скаржиться на E501 для довгого рядкового літерала — розбити його неявною конкатенацією, не змінюючи значення.
- **Тільки читання.** Конектор нічого не пише; міграцій немає; `services/limits.py` не змінюється.
- **Сумісність:** `one_time` за замовчуванням `"all"` — суми наявних інструментів не змінюються. Нові поля лише додаються (з типовими значеннями в схемах), наявні не змінюють значень.
- **Разові:** `one_time_amount` — частина суми рядка з `is_one_time = true`; `"exclude"` → `is_one_time IS FALSE`, `"only"` → `IS TRUE`.
- **Ліміти:** цифри `get_limit_progress` — з `services.limits.limit_progress`, тобто ті самі, що в `/limits`; `spent` без разових. Порядок періодів: місяць, потім тиждень.
- **Інструменти:** назва англійською, `title` українською, опис англійською й фактичний; `ToolAnnotations(read_only_hint=True, open_world_hint=False)`.
- **Логи ніколи не містять** аргументів, сум, назв категорій, імен.
- **Мова:** код, докстрінги, commit-меседжі — англійською; prose у `README.md` і `CLAUDE.md` — українською. Conventional commits, кожен коміт закінчується рядком `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Тести:** справжній SQLite-файл (фікстури `budget_db` / `budget_writer` / `readonly_session_factory`), очікувані значення пораховані вручну, без моків БД.

## Review Focus

1. **Межа періоду в `get_limit_progress` для минулої дати** — витрата о 00:10 Києва 15.09 має потрапити в тиждень 14–20.09, а не в попередній (тест у Task 4).
2. **Ліміт, змінений після кінця періоду** — для вересня має братись версія, чинна 30.09, а не жовтнева (тест у Task 4).
3. **Дата сьогодні** — `complete: false`, `forecast` екстраполює; дата в майбутньому — помилка з сьогоднішньою датою (тести в Task 4).
4. **`one_time: "only"` при порожньому результаті** — нулі й порожні списки, не ділення на нуль у `share_percent` (тест у Task 1).
5. **Сумісність контракту** — для даних без разових структурований вихід наявних інструментів відрізняється лише новими полями (оновлені точні тести в Task 1 і Task 3).

## File Structure

Шляхи — відносно `tg-bot/`, крім `CLAUDE.md` у корені репозиторію.

| Файл | Дія | Відповідальність | Задача |
|---|---|---|---|
| `src/budget_bot/connector/schemas.py` | змінити | `OneTimeFilter`, поля разових; схеми прогресу лімітів | 1, 2, 3, 4 |
| `src/budget_bot/connector/analytics.py` | змінити | `one_time` у `_conditions`, суми разових; `limit_progress_report` | 1, 2, 3, 4 |
| `src/budget_bot/connector/inputs.py` | змінити | публічний `parse_day` | 4 |
| `src/budget_bot/connector/tools.py` | змінити | аргумент `one_time`; інструмент `get_limit_progress` | 1, 2, 3, 4 |
| `tests/conftest.py` | змінити | `BudgetWriter.add_expense(one_time=…)`, `BudgetWriter.set_limit` | 1, 4 |
| `tests/test_connector_summary.py` | змінити | разові в підсумку | 1 |
| `tests/test_connector_trend.py` | змінити | разові в тренді | 2 |
| `tests/test_connector_list.py` | змінити | разові в списку | 3 |
| `tests/test_connector_limits.py` | створити | прогрес лімітів | 4 |
| `tests/test_connector_tools.py` | змінити | контракт MCP | 1, 3, 4 |
| `README.md`, `CLAUDE.md` | змінити | опис конектора, статус | 5 |

---

### Task 1: `one_time` filter and amounts in `summarize_spending`

**Files:**
- Modify: `src/budget_bot/connector/schemas.py`, `src/budget_bot/connector/analytics.py`, `src/budget_bot/connector/tools.py`, `tests/conftest.py`
- Test: `tests/test_connector_summary.py`, `tests/test_connector_tools.py`

**Interfaces:**
- Consumes: `Expense.is_one_time` (Phase 2 A).
- Produces:
  - `schemas.OneTimeFilter = Literal["all", "exclude", "only"]`
  - `CategorySpending.one_time_amount: int = 0`, `MemberSpending.one_time_amount: int = 0`, `SpendingSummary.one_time: OneTimeFilter = "all"`, `SpendingSummary.one_time_amount: int = 0`
  - `analytics._conditions(date_range, category, member, one_time: OneTimeFilter = "all")`
  - `analytics.summarize_spending(session, date_range, *, category, member, one_time: OneTimeFilter = "all")`
  - `tools.OneTimeArg` (annotated argument type reused by Tasks 2–3)
  - `BudgetWriter.add_expense(..., one_time: bool = False)`
  - test fixture `september_one_time` in `tests/conftest.py`

- [ ] **Step 1: Extend the test writer and add the fixture**

In `tests/conftest.py`, `BudgetWriter.add_expense`: add the keyword `one_time: bool = False` after `description` and pass `is_one_time=one_time` to `create_expense`. Append the fixture after `early_september`:

```python
@pytest_asyncio.fixture
async def september_one_time(early_september, budget_writer) -> None:
    """``early_september`` plus two one-time expenses (ids 6 and 7):

    | id | when (Kyiv)      | amount | category | member | one-time |
    |----|------------------|--------|----------|--------|----------|
    | 6  | 2026-09-10 10:00 | 5000   | Діти     | Оля    | yes      |
    | 7  | 2026-09-12 10:00 | 300    | Їжа      | Сергій | yes      |
    """
    add = budget_writer.add_expense
    await add(category="Діти", member="Оля", amount=5000, at=kyiv(2026, 9, 10, 10), one_time=True)
    await add(category="Їжа", member="Сергій", amount=300, at=kyiv(2026, 9, 12, 10), one_time=True)
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_connector_summary.py`:

```python
async def _summary(session_factory, one_time):
    async with session_factory() as session:
        return await summarize_spending(
            session, SEPTEMBER_1_TO_14, category=None, member=None, one_time=one_time
        )


async def test_summary_all_reports_one_time_parts(september_one_time, readonly_session_factory):
    summary = await _summary(readonly_session_factory, "all")

    assert summary.one_time == "all"
    assert (summary.total, summary.one_time_amount, summary.expense_count) == (6850, 5300, 5)
    assert summary.by_category == [
        CategorySpending(name="Діти", amount=5000, share_percent=73.0, count=1, one_time_amount=5000),
        CategorySpending(name="Їжа", amount=1750, share_percent=25.5, count=3, one_time_amount=300),
        CategorySpending(name="Транспорт", amount=100, share_percent=1.5, count=1),
    ]
    assert summary.by_member == [
        MemberSpending(name="Оля", amount=6300, count=3, one_time_amount=5000),
        MemberSpending(name="Сергій", amount=550, count=2, one_time_amount=300),
    ]


async def test_summary_exclude_is_regular_only(september_one_time, readonly_session_factory):
    summary = await _summary(readonly_session_factory, "exclude")

    assert (summary.total, summary.one_time_amount) == (1550, 0)
    assert [(c.name, c.amount, c.one_time_amount) for c in summary.by_category] == [
        ("Їжа", 1450, 0),
        ("Транспорт", 100, 0),
    ]


async def test_summary_only_one_time(september_one_time, readonly_session_factory):
    summary = await _summary(readonly_session_factory, "only")

    assert (summary.total, summary.one_time_amount, summary.expense_count) == (5300, 5300, 2)
    assert [(c.name, c.amount, c.share_percent) for c in summary.by_category] == [
        ("Діти", 5000, 94.3),
        ("Їжа", 300, 5.7),
    ]


async def test_summary_only_without_one_time_expenses_is_zero(
    early_september, readonly_session_factory
):
    summary = await _summary(readonly_session_factory, "only")

    assert (summary.total, summary.one_time_amount, summary.expense_count) == (0, 0, 0)
    assert (summary.by_category, summary.by_member) == ([], [])
```

In `tests/test_connector_tools.py`, update the expected dict in `test_results_arrive_as_structured_content` to the new contract:

```python
    assert result.structured_content == {
        "start_date": "2026-09-14",
        "end_date": "2026-09-14",
        "category": "Їжа",
        "member": None,
        "one_time": "all",
        "total": 1200,
        "one_time_amount": 0,
        "expense_count": 1,
        "by_category": [
            {
                "name": "Їжа",
                "amount": 1200,
                "share_percent": 100.0,
                "count": 1,
                "one_time_amount": 0,
            }
        ],
        "by_member": [{"name": "Оля", "amount": 1200, "count": 1, "one_time_amount": 0}],
    }
```

and append:

```python
async def test_summarize_accepts_one_time_filter(september_one_time, readonly_session_factory):
    result = await call(
        readonly_session_factory,
        "summarize_spending",
        {"start_date": "2026-09-01", "end_date": "2026-09-14", "one_time": "exclude"},
    )

    assert result.is_error is False
    assert result.structured_content["total"] == 1550
    assert result.structured_content["one_time"] == "exclude"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_connector_summary.py tests/test_connector_tools.py -q`
Expected: FAIL — `TypeError: summarize_spending() got an unexpected keyword argument 'one_time'` and the structured-content dict mismatch.

- [ ] **Step 4: Schemas**

In `src/budget_bot/connector/schemas.py` add after `SortOrder`:

```python
OneTimeFilter = Literal["all", "exclude", "only"]

ONE_TIME_AMOUNT = "Part of the amount marked in the bot as one-time (разова)"
```

Change the models (new fields last, with defaults):

```python
class CategorySpending(BaseModel):
    name: str
    amount: int
    share_percent: float = Field(description="Share of the total in percent, one decimal")
    count: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)


class MemberSpending(BaseModel):
    name: str
    amount: int
    count: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)


class SpendingSummary(BaseModel):
    start_date: dt.date
    end_date: dt.date
    category: str | None
    member: str | None
    one_time: OneTimeFilter = "all"
    total: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)
    expense_count: int
    by_category: list[CategorySpending]
    by_member: list[MemberSpending]
```

- [ ] **Step 5: Analytics**

In `src/budget_bot/connector/analytics.py`: import `case` from `sqlalchemy` and `OneTimeFilter` from schemas. Replace `_conditions`:

```python
def _conditions(
    date_range: DateRange,
    category: Category | None,
    member: Member | None,
    one_time: OneTimeFilter = "all",
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
    if one_time == "exclude":
        conditions.append(Expense.is_one_time.is_(False))
    elif one_time == "only":
        conditions.append(Expense.is_one_time.is_(True))
    return conditions
```

Add below `_conditions`:

```python
# Sum of the one-time part, usable next to func.sum(Expense.amount) in any grouping.
ONE_TIME_SUM = func.sum(case((Expense.is_one_time, Expense.amount), else_=0))
```

Replace `summarize_spending`:

```python
async def summarize_spending(
    session: AsyncSession,
    date_range: DateRange,
    *,
    category: Category | None,
    member: Member | None,
    one_time: OneTimeFilter = "all",
) -> SpendingSummary:
    conditions = _conditions(date_range, category, member, one_time)
    amount = func.sum(Expense.amount)
    category_rows = (
        await session.execute(
            select(Category.name, amount, func.count(Expense.id), ONE_TIME_SUM)
            .join(Category, Category.id == Expense.category_id)
            .where(*conditions)
            .group_by(Category.id, Category.name)
            .order_by(amount.desc(), Category.name)
        )
    ).all()
    member_rows = (
        await session.execute(
            select(Member.display_name, amount, func.count(Expense.id), ONE_TIME_SUM)
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
        one_time=one_time,
        total=total,
        one_time_amount=sum(row[3] for row in category_rows),
        expense_count=sum(row[2] for row in category_rows),
        by_category=[
            CategorySpending(
                name=name,
                amount=value,
                share_percent=round(value * 100 / total, 1),
                count=n,
                one_time_amount=part,
            )
            for name, value, n, part in category_rows
        ],
        by_member=[
            MemberSpending(name=name, amount=value, count=n, one_time_amount=part)
            for name, value, n, part in member_rows
        ],
    )
```

- [ ] **Step 6: Tool argument**

In `src/budget_bot/connector/tools.py` import `OneTimeFilter` from schemas and add after `MemberName`:

```python
OneTimeArg = Annotated[
    OneTimeFilter,
    Field(
        description="all: every expense; exclude: without expenses marked one-time (разова) "
        "in the bot; only: just those"
    ),
]
```

Append to `SUMMARY_DESCRIPTION` (keep it one string): `" Each amount also carries one_time_amount, the part marked one-time in the bot."`

In `summarize_spending` add the parameter `one_time: OneTimeArg = "all",` after `member` and pass `one_time=one_time` to `analytics.summarize_spending`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_connector_summary.py tests/test_connector_tools.py -q`
Expected: PASS (the pre-existing summary tests stay green thanks to the field defaults).

- [ ] **Step 8: Full suite, lint, commit**

Run: `.venv/bin/black src tests && .venv/bin/ruff check src tests && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/connector/schemas.py src/budget_bot/connector/analytics.py src/budget_bot/connector/tools.py tests/conftest.py tests/test_connector_summary.py tests/test_connector_tools.py
git commit -m "feat(connector): one-time filter and amounts in summarize_spending

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `one_time` in `get_spending_trend`

**Files:**
- Modify: `src/budget_bot/connector/schemas.py`, `src/budget_bot/connector/analytics.py`, `src/budget_bot/connector/tools.py`
- Test: `tests/test_connector_trend.py`

**Interfaces:**
- Consumes: `OneTimeFilter`, `_conditions(..., one_time)`, `OneTimeArg`, fixture `september_one_time` (Task 1).
- Produces: `BreakdownItem.one_time_amount: int = 0`, `TrendBucket.one_time_amount: int = 0`, `SpendingTrend.one_time: OneTimeFilter = "all"`; `analytics.spending_trend(..., one_time: OneTimeFilter = "all")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_connector_trend.py`:

```python
async def _weekly(session_factory, one_time, split_by="category"):
    async with session_factory() as session:
        return await spending_trend(
            session,
            SEPTEMBER_1_TO_14,
            granularity="week",
            split_by=split_by,
            category=None,
            member=None,
            one_time=one_time,
        )


async def test_trend_all_carries_one_time_parts(september_one_time, readonly_session_factory):
    trend = await _weekly(readonly_session_factory, "all")

    assert trend.one_time == "all"
    assert [(b.total, b.one_time_amount) for b in trend.buckets] == [
        (350, 0),
        (5300, 5300),
        (1200, 0),
    ]
    assert trend.buckets[1].breakdown == [
        BreakdownItem(name="Діти", amount=5000, count=1, one_time_amount=5000),
        BreakdownItem(name="Їжа", amount=300, count=1, one_time_amount=300),
    ]


@pytest.mark.parametrize(
    ("one_time", "totals"),
    [("exclude", [350, 0, 1200]), ("only", [0, 5300, 0])],
)
async def test_trend_one_time_filter(
    september_one_time, readonly_session_factory, one_time, totals
):
    trend = await _weekly(readonly_session_factory, one_time, split_by="none")

    assert [b.total for b in trend.buckets] == totals
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_connector_trend.py -q`
Expected: FAIL — `TypeError: spending_trend() got an unexpected keyword argument 'one_time'`.

- [ ] **Step 3: Implement**

`schemas.py`:

```python
class BreakdownItem(BaseModel):
    name: str
    amount: int
    count: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)


class TrendBucket(BaseModel):
    start_date: dt.date
    end_date: dt.date
    partial: bool = Field(description="True when the date range cuts this week or month short")
    total: int
    count: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)
    breakdown: list[BreakdownItem] | None


class SpendingTrend(BaseModel):
    start_date: dt.date
    end_date: dt.date
    granularity: Granularity
    split_by: SplitBy
    category: str | None
    member: str | None
    one_time: OneTimeFilter = "all"
    buckets: list[TrendBucket]
```

`analytics.py` — replace `spending_trend` and `_breakdown`:

```python
async def spending_trend(
    session: AsyncSession,
    date_range: DateRange,
    *,
    granularity: Granularity,
    split_by: SplitBy,
    category: Category | None,
    member: Member | None,
    one_time: OneTimeFilter = "all",
) -> SpendingTrend:
    spans = trend_buckets(date_range, granularity)
    rows = (
        await session.execute(
            select(
                Expense.created_at,
                Expense.amount,
                Expense.is_one_time,
                Category.name,
                Member.display_name,
            )
            .join(Category, Category.id == Expense.category_id)
            .join(Member, Member.id == Expense.member_id)
            .where(*_conditions(date_range, category, member, one_time))
        )
    ).all()

    starts = [span.first for span in spans]
    totals = [0] * len(spans)
    counts = [0] * len(spans)
    one_time_parts = [0] * len(spans)
    # name -> [amount, count, one-time amount]
    groups: list[defaultdict[str, list[int]]] = [defaultdict(lambda: [0, 0, 0]) for _ in spans]
    for created_at, amount, is_one_time, category_name, member_name in rows:
        index = bisect_right(starts, to_kyiv(created_at).date()) - 1
        part = amount if is_one_time else 0
        totals[index] += amount
        counts[index] += 1
        one_time_parts[index] += part
        if split_by != "none":
            entry = groups[index][category_name if split_by == "category" else member_name]
            entry[0] += amount
            entry[1] += 1
            entry[2] += part

    return SpendingTrend(
        start_date=date_range.first,
        end_date=date_range.last,
        granularity=granularity,
        split_by=split_by,
        category=category.name if category is not None else None,
        member=member.display_name if member is not None else None,
        one_time=one_time,
        buckets=[
            TrendBucket(
                start_date=span.first,
                end_date=span.last,
                partial=span.partial,
                total=totals[index],
                count=counts[index],
                one_time_amount=one_time_parts[index],
                breakdown=None if split_by == "none" else _breakdown(groups[index]),
            )
            for index, span in enumerate(spans)
        ],
    )
```

```python
def _breakdown(group: dict[str, list[int]]) -> list[BreakdownItem]:
    ordered = sorted(group.items(), key=lambda item: (-item[1][0], item[0]))
    return [
        BreakdownItem(name=name, amount=amount, count=n, one_time_amount=part)
        for name, (amount, n, part) in ordered
    ]
```

`tools.py` — in `get_spending_trend` add `one_time: OneTimeArg = "all",` after `member` and pass `one_time=one_time`; append to `TREND_DESCRIPTION`: `" Each bucket and breakdown row also carries one_time_amount, the part marked one-time in the bot."`

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_connector_trend.py tests/test_connector_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite, lint, commit**

Run: `.venv/bin/black src tests && .venv/bin/ruff check src tests && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/connector/schemas.py src/budget_bot/connector/analytics.py src/budget_bot/connector/tools.py tests/test_connector_trend.py
git commit -m "feat(connector): one-time filter and amounts in get_spending_trend

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `one_time` in `list_expenses`

**Files:**
- Modify: `src/budget_bot/connector/schemas.py`, `src/budget_bot/connector/analytics.py`, `src/budget_bot/connector/tools.py`
- Test: `tests/test_connector_list.py`, `tests/test_connector_tools.py`

**Interfaces:**
- Consumes: `_conditions(..., one_time)`, `OneTimeArg`, fixture `september_one_time` (Task 1).
- Produces: `ExpenseItem.is_one_time: bool = False`; `analytics.list_expenses(..., one_time: OneTimeFilter = "all")`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_connector_list.py`, add `"one_time": "all",` to the default `arguments` dict in `list_page` (after `"offset": 0`), and add `"is_one_time": False,` to the expected dict in `test_items_carry_the_bot_id_kyiv_time_and_names` (after `"description": "Сільпо"`). Append:

```python
async def test_items_flag_one_time(september_one_time, readonly_session_factory):
    page = await list_page(readonly_session_factory, sort="largest")

    assert [(item.amount, item.is_one_time) for item in page.items] == [
        (5000, True),
        (1200, False),
        (600, False),
        (350, False),
        (300, True),
        (250, False),
        (100, False),
    ]


@pytest.mark.parametrize(
    ("one_time", "amounts"),
    [("only", [300, 5000]), ("exclude", [600, 1200, 100, 250, 350])],
)
async def test_one_time_filter(september_one_time, readonly_session_factory, one_time, amounts):
    page = await list_page(readonly_session_factory, one_time=one_time)

    assert [item.amount for item in page.items] == amounts
    assert page.total_count == len(amounts)
```

In `tests/test_connector_tools.py` append:

```python
async def test_list_expenses_accepts_one_time_filter(
    september_one_time, readonly_session_factory
):
    result = await call(readonly_session_factory, "list_expenses", {**SEPTEMBER, "one_time": "only"})

    assert result.is_error is False
    items = result.structured_content["items"]
    assert [(item["amount"], item["is_one_time"]) for item in items] == [(300, True), (5000, True)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_connector_list.py tests/test_connector_tools.py -q`
Expected: FAIL — `TypeError: list_expenses() got an unexpected keyword argument 'one_time'`.

- [ ] **Step 3: Implement**

`schemas.py` — `ExpenseItem` gains, after `description`:

```python
    is_one_time: bool = Field(False, description="True when marked one-time (разова) in the bot")
```

`analytics.py`, `list_expenses`: add the keyword `one_time: OneTimeFilter = "all",` after `offset: int,`; add `Expense.is_one_time,` to the selected columns (after `Expense.description,`); pass `one_time` into `_conditions(date_range, category, member, one_time)`; add `is_one_time=row.is_one_time,` to the `ExpenseItem(...)` construction.

`tools.py`, `list_expenses`: add `one_time: OneTimeArg = "all",` after `min_amount` and pass `one_time=one_time`; append to `LIST_DESCRIPTION`: `" Each item says whether it is marked one-time in the bot."`

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_connector_list.py tests/test_connector_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite, lint, commit**

Run: `.venv/bin/black src tests && .venv/bin/ruff check src tests && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/connector/schemas.py src/budget_bot/connector/analytics.py src/budget_bot/connector/tools.py tests/test_connector_list.py tests/test_connector_tools.py
git commit -m "feat(connector): one-time filter and flag in list_expenses

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `get_limit_progress` tool

**Files:**
- Modify: `src/budget_bot/connector/inputs.py`, `src/budget_bot/connector/schemas.py`, `src/budget_bot/connector/analytics.py`, `src/budget_bot/connector/tools.py`, `tests/conftest.py`
- Create: `tests/test_connector_limits.py`
- Test: `tests/test_connector_tools.py`

**Interfaces:**
- Consumes: `services.limits.limit_progress`, `period_days`, `LIMIT_PERIODS` (Phase 2 A); `periods.period_range`, `kyiv_day_range`, `to_kyiv`.
- Produces:
  - `inputs.parse_day(name: str, raw: str) -> date` (the former private `_parse_day`, renamed)
  - schemas `LimitStatusName`, `LimitItem`, `LimitPeriodProgress`, `LimitProgressReport`
  - `analytics.limit_progress_report(session, day: date, *, now_utc: datetime) -> LimitProgressReport`
  - MCP tool `get_limit_progress(date: str | None = None)`
  - `BudgetWriter.set_limit(*, period: str, category: str | None, amount: int, at: datetime)`

- [ ] **Step 1: Extend the test writer**

In `tests/conftest.py` add `from budget_bot.periods import KYIV, Period` (merge with the existing `KYIV` import) and `from budget_bot.services.limits import set_limit`; add this method to `BudgetWriter`:

```python
    async def set_limit(
        self, *, period: str, category: str | None, amount: int, at: datetime
    ) -> None:
        async with self._factory() as db_session:
            category_id = (
                await db_session.scalar(select(Category.id).where(Category.name == category))
                if category is not None
                else None
            )
            member_id = await db_session.scalar(
                select(Member.id).where(Member.display_name == "Сергій")
            )
            await set_limit(
                db_session,
                household_id=SINGLETON_HOUSEHOLD_ID,
                member_id=member_id,
                period_type=Period(period),
                category_id=category_id,
                amount=amount,
                now=at,
            )
            await db_session.commit()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_connector_limits.py`:

```python
from datetime import date

import pytest
import pytest_asyncio

from budget_bot.connector.analytics import limit_progress_report
from budget_bot.connector.inputs import InvalidRequest
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)  # Thursday; week 12.10–18.10, day 15 of October


@pytest_asyncio.fixture
async def limits_history(september_one_time, budget_writer) -> None:
    """September data from ``september_one_time`` plus limits and one October expense.

    - Їжа, month: 10 000 from 05.09, raised to 12 000 on 02.10.
    - General, week: 3 000 from 01.09.
    - 03.10: Їжа 3 000 (regular).
    """
    await budget_writer.set_limit(period="month", category="Їжа", amount=10000, at=kyiv(2026, 9, 5))
    await budget_writer.set_limit(period="month", category="Їжа", amount=12000, at=kyiv(2026, 10, 2))
    await budget_writer.set_limit(period="week", category=None, amount=3000, at=kyiv(2026, 9, 1))
    await budget_writer.add_expense(
        category="Їжа", member="Оля", amount=3000, at=kyiv(2026, 10, 3)
    )


async def report(session_factory, day):
    async with session_factory() as session:
        return await limit_progress_report(session, day, now_utc=NOW)


async def test_current_periods(limits_history, readonly_session_factory):
    result = await report(readonly_session_factory, date(2026, 10, 15))

    month, week = result.periods
    assert result.date == date(2026, 10, 15)
    assert (month.period_type, month.start_date, month.end_date) == (
        "month",
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    assert (month.day_index, month.days_in_period, month.complete) == (15, 31, False)
    assert [item.model_dump() for item in month.limits] == [
        {
            "category": "Їжа",
            "amount": 12000,
            "spent": 3000,
            "percent": 25,
            "remaining": 9000,
            "forecast": 6200,  # 3000 / 15 * 31
            "status": "ok",
        }
    ]
    assert (week.start_date, week.end_date, week.day_index, week.complete) == (
        date(2026, 10, 12),
        date(2026, 10, 18),
        4,
        False,
    )
    assert [(i.category, i.amount, i.spent, i.forecast) for i in week.limits] == [
        (None, 3000, 0, 0)
    ]


async def test_past_month_uses_the_limit_in_force_at_its_end(
    limits_history, readonly_session_factory
):
    result = await report(readonly_session_factory, date(2026, 9, 14))

    month, week = result.periods
    assert (month.start_date, month.end_date) == (date(2026, 9, 1), date(2026, 9, 30))
    assert (month.day_index, month.days_in_period, month.complete) == (30, 30, True)
    # 250 + 1200 regular Їжа in September; the 300 one-time and 31.08 are excluded.
    assert [(i.category, i.amount, i.spent, i.percent, i.forecast) for i in month.limits] == [
        ("Їжа", 10000, 1450, 14, 1450)
    ]
    # Week 14.09–20.09: 1200 (14.09 23:30) + 600 (15.09 00:10 Kyiv).
    assert (week.start_date, week.end_date, week.complete) == (
        date(2026, 9, 14),
        date(2026, 9, 20),
        True,
    )
    assert [(i.category, i.spent, i.percent, i.forecast, i.status) for i in week.limits] == [
        (None, 1800, 60, 1800, "ok")
    ]


async def test_no_limits_gives_empty_lists(early_september, readonly_session_factory):
    result = await report(readonly_session_factory, date(2026, 9, 14))

    assert [period.limits for period in result.periods] == [[], []]


async def test_future_date_is_rejected_with_today(readonly_session_factory):
    with pytest.raises(InvalidRequest, match="today in Kyiv is 2026-10-15"):
        await report(readonly_session_factory, date(2026, 10, 16))
```

In `tests/test_connector_tools.py`: add `"get_limit_progress"` to the expected tool-name set in `test_every_tool_is_titled_and_read_only`, add this case to the `test_fixable_mistakes_come_back_as_errors_with_a_hint` parametrize list:

```python
        ("get_limit_progress", {"date": "2100-12-31"}, "is in the future"),
        ("get_limit_progress", {"date": "14.09.2026"}, "YYYY-MM-DD"),
```

and append:

```python
async def test_limit_progress_for_a_past_day(early_september, budget_writer, readonly_session_factory):
    await budget_writer.set_limit(period="week", category=None, amount=3000, at=kyiv(2026, 9, 1))

    result = await call(readonly_session_factory, "get_limit_progress", {"date": "2026-09-14"})

    assert result.is_error is False
    week = result.structured_content["periods"][1]
    assert (week["period_type"], week["start_date"], week["complete"]) == (
        "week",
        "2026-09-14",
        True,
    )
    assert week["limits"][0]["spent"] == 1800
```

(add `from tests.conftest import kyiv` to that module's imports).

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_connector_limits.py tests/test_connector_tools.py -q`
Expected: FAIL — `ImportError: cannot import name 'limit_progress_report'`.

- [ ] **Step 4: Public `parse_day`**

In `src/budget_bot/connector/inputs.py` rename `_parse_day` to `parse_day` (definition and both calls in `parse_date_range`).

- [ ] **Step 5: Schemas**

Append to `src/budget_bot/connector/schemas.py`:

```python
LimitStatusName = Literal["ok", "warn", "over"]


class LimitItem(BaseModel):
    category: str | None = Field(description="Category name; null for the household-wide limit")
    amount: int = Field(description="The limit, UAH")
    spent: int = Field(description="Spending in the period without expenses marked one-time")
    percent: int = Field(description="spent * 100 // amount")
    remaining: int = Field(description="amount - spent; negative when over the limit")
    forecast: int = Field(
        description="spent / day_index * days_in_period, rounded; equals spent once complete"
    )
    status: LimitStatusName = Field(
        description="over: percent >= 100; warn: percent >= 80 or forecast > amount; else ok"
    )


class LimitPeriodProgress(BaseModel):
    period_type: Literal["month", "week"]
    start_date: dt.date
    end_date: dt.date
    day_index: int = Field(description="Day of the period the figures are for, from 1")
    days_in_period: int
    complete: bool = Field(description="True when the period has already ended")
    limits: list[LimitItem]


class LimitProgressReport(BaseModel):
    date: dt.date
    periods: list[LimitPeriodProgress] = Field(
        description="The calendar month and the Monday-to-Sunday week containing date, in Kyiv"
    )
```

- [ ] **Step 6: Analytics**

In `src/budget_bot/connector/analytics.py` add imports: `LimitItem`, `LimitPeriodProgress`, `LimitProgressReport` (schemas); `period_range` (periods, next to `kyiv_day_range, to_kyiv`); `from budget_bot.services.limits import LIMIT_PERIODS, limit_progress, period_days`. Append:

```python
async def limit_progress_report(
    session: AsyncSession, day: date, *, now_utc: datetime
) -> LimitProgressReport:
    """Limit progress for the month and the week containing ``day``.

    Figures come from services.limits, as in the bot's /limits. A past period
    is evaluated at its last moment, so it uses the limits in force at its end
    and its forecast equals what was spent.
    """
    today = to_kyiv(now_utc).date()
    if day > today:
        raise InvalidRequest(
            f"date {day.isoformat()} is in the future; today in Kyiv is {today.isoformat()}"
        )

    anchor = kyiv_day_range(day, day).start
    periods = []
    for period_type in LIMIT_PERIODS:
        bounds = period_range(period_type, anchor)
        as_of = min(now_utc, bounds.end - timedelta(microseconds=1))
        day_index, days_in_period = period_days(bounds, as_of)
        progress = await limit_progress(session, HOUSEHOLD_ID, period_type, as_of)
        periods.append(
            LimitPeriodProgress(
                period_type=period_type.value,
                start_date=to_kyiv(bounds.start).date(),
                end_date=to_kyiv(bounds.end).date() - timedelta(days=1),
                day_index=day_index,
                days_in_period=days_in_period,
                complete=now_utc >= bounds.end,
                limits=[
                    LimitItem(
                        category=item.category_name,
                        amount=item.amount,
                        spent=item.spent,
                        percent=item.percent,
                        remaining=item.remaining,
                        forecast=item.forecast,
                        status=item.status.value,
                    )
                    for item in progress
                ],
            )
        )
    return LimitProgressReport(date=day, periods=periods)
```

- [ ] **Step 7: The tool**

In `src/budget_bot/connector/tools.py` import `parse_day` (inputs), `LimitProgressReport` (schemas), `to_kyiv` from `budget_bot.periods`. Add after `LIST_DESCRIPTION`:

```python
LIMITS_DESCRIPTION = (
    "Returns spending limits set in the bot with their progress, for the calendar month and "
    "the Monday-to-Sunday week (Kyiv time) containing the given day, today by default: the "
    "limit in whole UAH, spending so far without expenses marked one-time, percent used, "
    "remaining, a linear forecast for the whole period and a status. A past period uses the "
    "limits in force at its end. Category null means the household-wide limit."
)
```

Register it inside `build_mcp_server`, after `list_expenses`:

```python
    @server.tool(
        name="get_limit_progress",
        title="Прогрес лімітів",
        description=LIMITS_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def get_limit_progress(
        ctx: Context,
        date: Annotated[
            str | None,
            Field(description="A Kyiv calendar day, YYYY-MM-DD, not in the future; default today"),
        ] = None,
    ) -> LimitProgressReport:
        async def work(session: AsyncSession) -> LimitProgressReport:
            now = utcnow()
            day = parse_day("date", date) if date is not None else to_kyiv(now).date()
            return await analytics.limit_progress_report(session, day, now_utc=now)

        return await _run("get_limit_progress", ctx, session_factory, work)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_connector_limits.py tests/test_connector_tools.py tests/test_connector_inputs.py -q`
Expected: PASS.

- [ ] **Step 9: Full suite, lint, commit**

Run: `.venv/bin/black src tests && .venv/bin/ruff check src tests && .venv/bin/python -m pytest -q`

```bash
git add src/budget_bot/connector/inputs.py src/budget_bot/connector/schemas.py src/budget_bot/connector/analytics.py src/budget_bot/connector/tools.py tests/conftest.py tests/test_connector_limits.py tests/test_connector_tools.py
git commit -m "feat(connector): get_limit_progress tool

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Docs and final verification

**Files:**
- Modify: `README.md` (in `tg-bot/`), `CLAUDE.md` (repo root)

**Interfaces:** none.

- [ ] **Step 1: README**

In `tg-bot/README.md`, section «Claude-конектор», replace

```
чотири інструменти — огляд бюджету, підсумок за період, динаміку по тижнях чи
місяцях і список записів.
```

with

```
п'ять інструментів — огляд бюджету, підсумок за період, динаміку по тижнях чи
місяцях, список записів і прогрес лімітів (поточний або за минулий тиждень /
місяць). Підсумок, динаміка й список розрізняють разові витрати: окремі суми
«з них разових» і фільтр `one_time`.
```

- [ ] **Step 2: CLAUDE.md**

In `CLAUDE.md`, section «Статус», in the Phase 2 paragraph, replace `Підпроєкт A реалізовано:` with `Підпроєкти A і C реалізовано. C: конектор віддає прогрес лімітів (`get_limit_progress`) і разові витрати. A:` — keep the rest of the sentence.

- [ ] **Step 3: Full verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/black --check src tests`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add README.md ../CLAUDE.md
git commit -m "docs: connector limits and one-time expenses

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Manual check after deploy (for the user)**

У claude.ai з підключеним конектором: «Який прогрес лімітів цього місяця?» — цифри збігаються з `/limits` у боті; «Скільки ми витратили у вересні без разових?» — сума збігається з `/report` мінус «з них разових».
