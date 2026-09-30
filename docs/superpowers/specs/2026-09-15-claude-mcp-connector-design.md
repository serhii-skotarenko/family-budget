# Claude-конектор (MCP) до сімейного бюджету — дизайн

**Дата:** 2026-09-15 · **Статус:** дизайн затверджено в брейнштормінгу, специфікація чекає на рев'ю ·
**Гілка:** `feat/claude-mcp-connector`

> **Оновлення 2026-09-30 (Phase 2, підпроєкт C, гілка `feat/phase2-connector-limits`).** Після
> підпроєкту A (`2026-09-30-phase2-a-limits-one-time-design.md`) у даних з'явились ліміти й
> позначка «разова». Конектор отримує п'ятий інструмент `get_limit_progress` і аргумент / поля
> для разових витрат у наявних трьох. Нові місця позначені «(Phase 2 C)». Усе інше в цьому
> документі — без змін: лише читання, та сама автентифікація, той самий read-only engine.

## Мета

Дати Claude доступ на читання до витрат із бота, щоб у звичайному чаті розбиратися з фінансами:
скільки й на що йде грошей, як це змінюється, які записи за цим стоять. Клієнти — claude.ai,
Claude Desktop, мобільний застосунок Claude і Claude Code.

Це розширення поза межами MVP з `docs/requirements.md`. Поведінка бота і схема БД не змінюються,
міграцій немає (Phase 2 C теж без міграцій: читає таблицю `limits` і `expenses.is_one_time`,
додані в підпроєкті A).

## Ухвалені рішення

| Питання | Рішення |
|---|---|
| Поверхня | Remote MCP-сервер, підключений як custom connector |
| Клієнти | claude.ai, Desktop і мобільний (спільна інфраструктура конекторів), Claude Code |
| Дані | лише витрати з бота: учасники, категорії, записи |
| Доступ | тільки читання |
| Авторизація | статичний заголовок `Authorization: Bearer <токен>`, окремий токен на людину |
| Форма API | аналітика на сервері + сторінкові деталі, 5 інструментів (п'ятий — Phase 2 C) |
| Розміщення | той самий процес і контейнер Railway, що й бот |

## Свідомо не включено

- OAuth (DCR/CIMD) і будь-який сервер авторизації.
- Rate limiting.
- Окремий Railway-сервіс: том монтується лише в один сервіс.
- Запис, редагування чи видалення через MCP.
- Доходи — їх немає в даних. (Ліміти й разові витрати додано в Phase 2 C.)
- Запис лімітів через MCP (встановлення / зняття — лише в боті).
- Відносні періоди («цього місяця»), окремий інструмент «топ витрат», порівняння періодів.
- MCP resources і prompts.
- SSE-стріми та stateful-сесії.

## Архітектура

```
Railway, один контейнер
┌────────────────────────────────────────────────────┐
│ python -m budget_bot — один asyncio-процес         │
│   ├─ aiogram polling ─── пише ──┐                  │
│   └─ uvicorn 0.0.0.0:$PORT      ▼                  │
│        /mcp ─── читає ─── /data/budget.sqlite3     │
│        BearerGate → MCPServer (stateless, JSON)    │
└────────────────────────────────────────────────────┘
        ▲ HTTPS
        ├─ claude.ai / Desktop / мобільний  (з мережі Anthropic, заголовок у налаштуваннях конектора)
        └─ Claude Code                       (з ноутбука, --header)
```

### Компоненти

| Модуль | Відповідальність | Залежить від |
|---|---|---|
| `budget_bot/connector/schemas.py` | Pydantic-моделі відповідей інструментів — публічний контракт API | — |
| `budget_bot/connector/analytics.py` | Запити й агрегація для огляду, підсумку, тренду, списку і (Phase 2 C) прогресу лімітів. Приймає `AsyncSession` і провалідовані значення, повертає моделі зі `schemas.py`, на некоректний запит кидає `InvalidRequest` | `models`, `periods`, `services` |
| `budget_bot/connector/tools.py` | `build_mcp_server(session_factory) -> MCPServer`: реєстрація 5 інструментів (назва, `title`, опис, анотації), розбір аргументів, мапінг помилок, лог виклику | `analytics`, SDK |
| `budget_bot/services/limits.py` (Phase 2 C) | Без змін; `limit_progress` викликається з `analytics` для обчислення прогресу — ті самі цифри, що в `/limits` | — |
| `budget_bot/connector/auth.py` | Розбір `MCP_ACCESS_TOKENS`; ASGI-middleware `BearerGate` | — |
| `budget_bot/connector/server.py` | Збирає ASGI-застосунок (`BearerGate` поверх Starlette-застосунку SDK), `uvicorn.Server` без перехоплення сигналів і `serve_connector()`, яка не випускає збій назовні | `auth`, `tools` |
| `budget_bot/db.py` | + `create_readonly_engine(database_path)` | — |
| `budget_bot/periods.py` | + публічний `kyiv_day_range(first, last, label) -> PeriodRange`; `parse_custom_range` переходить на нього замість приватного `_kyiv_midnight_as_utc` | — |
| `budget_bot/config.py` | + `MCP_ACCESS_TOKENS`, `MCP_PUBLIC_HOST`, `PORT` | — |
| `budget_bot/__main__.py` | Композиція: вмикає конектор за наявності конфігу, запускає його поруч із polling, керує порядком зупинки | усе вище |

`services/reports.py` не змінюється. У конектора власна агрегація: вона додає кількість записів
і фільтри за категорією та учасником. Узгодженість із `/report` перевіряє тест (див. «Тестування»).

### Потік запиту

1. Клієнт Claude надсилає `POST https://<домен>/mcp` із `Authorization: Bearer <токен>`.
2. `BearerGate` звіряє токен. Якщо він валідний, мітка токена кладеться в
   `scope["state"]["mcp_token_label"]`; інакше клієнт отримує `401`, і запит далі не йде.
3. Застосунок SDK перевіряє `Host`, `Origin` і `Content-Type`, розбирає JSON-RPC і викликає
   інструмент.
4. Інструмент відкриває сесію на read-only engine, викликає `analytics` і повертає Pydantic-модель.
   SDK віддає її як structured output разом із текстовим JSON.
5. У лог пишеться мітка, назва інструмента, результат і тривалість.

## Безпека

### Автентифікація

- Формат `MCP_ACCESS_TOKENS`: `label:token,label:token`. Мітка відповідає `[a-z0-9_-]{1,32}`.
  Токен має щонайменше 32 символи; рядок ділиться за першою `:`. Мітки й токени мають бути
  унікальними.
- `BearerGate` — чиста ASGI-middleware. Скоупи `http` перевіряє, а `lifespan` пропускає без змін:
  через lifespan SDK запускає свій session manager.
- Очікуваний заголовок — `Authorization: Bearer <токен>`, назва схеми без урахування регістру.
  Порівняння — `hmac.compare_digest` з **кожним** налаштованим токеном, без раннього виходу.
- Відмова: `401`, заголовок `WWW-Authenticate: Bearer`, тіло `Unauthorized`, **без**
  `resource_metadata`. Тому й не `TokenVerifier` з SDK: він завжди додає посилання на
  OAuth-метадані, і Claude спробував би пройти OAuth, якого в нас немає.
- Гейт обгортає застосунок SDK напряму, без `Mount`. SDK реєструє `/mcp` як `Route`, тож
  запит на `/mcp` не редиректиться. Редирект відкинув би заголовок `Authorization`.

### Host і Origin (захист від DNS rebinding)

- `TransportSecuritySettings(enable_dns_rebinding_protection=True,
  allowed_hosts=[MCP_PUBLIC_HOST], allowed_origins=["https://claude.ai"])`.
- Поведінка SDK: хост звіряється точно (або за шаблоном `host:*`); запит без `Origin`
  пропускається. Чужий `Host` дає `421`, чужий `Origin` — `403`, POST не з JSON — `400`.

### База лише для читання

- Окремий engine: `sqlite+aiosqlite:///file:<path>?mode=ro&uri=true`. На кожне з'єднання —
  `PRAGMA query_only=ON` і `PRAGMA busy_timeout=10000`. Прагм `journal_mode` і `foreign_keys`
  немає: перша вимагає запису, друга для читання не потрібна.
- Перевірено експериментом 2026-09-14 на WAL-базі з engine бота:
  - читання працює і тоді, коли бот тримає з'єднання, і тоді, коли не тримає;
  - `INSERT` падає з `attempt to write a readonly database`;
  - коміти бота видно без помилок блокування;
  - read-only з'єднання може залишити файли `-wal` і `-shm` — це нешкідливо, бот їх підхоплює.
- Кожен виклик інструмента — одна сесія і одна транзакція читання, тож цифри в межах одного
  виклику узгоджені між собою.

### Логи

- Виклик інструмента: INFO `MCP tool <name> by <label>: <ok|invalid_request|internal_error> in <ms> ms`.
  Мітка береться з `ctx.request_context.request.state`; для викликів у процесі (тести) —
  `-`.
- Відмова гейта: WARNING із причиною (`missing` або `invalid`) і адресою клієнта — останній хоп
  `X-Forwarded-For` (його дописує edge-проксі; попередні клієнт може підробити), інакше адреса
  з'єднання.
- Непередбачений виняток: `logger.exception` із назвою інструмента.
- **Ніколи не логуються:** значення токенів, суми, описи, назви категорій, імена та аргументи
  викликів (`search` містить довільний текст).
- uvicorn: `log_config=None` (спільний `logging.basicConfig` застосунку), `access_log=False`.
- SDK сам пише текст кожного `ToolError` у лог на рівні INFO (логер
  `mcp.server.mcpserver.server`), а наші повідомлення містять назви категорій і учасників.
  Тому рівень цього логера — WARNING: попередження й помилки SDK лишаються в лозі.

### Секрети

Токени генеруються локально і в Railway зберігаються як sealed-змінна. У репозиторій, чат і
логи вони не потрапляють.

## Інструменти (API)

### Спільні правила

- **Дати.** `start_date` і `end_date` — рядки `YYYY-MM-DD`, обидві включно, календарні дні
  Europe/Kyiv. Розбирає їх наш код, а не валідація SDK, тож усі повідомлення про помилки
  контрольовані. Допустимі роки — 2000–2100; `end_date` раніше за `start_date` — помилка.
- **Дата витрати** — момент запису в боті (`Expense.created_at`); окремої дати покупки немає.
  Описи інструментів кажуть це прямо.
- **Суми** — цілі гривні (`int`), валюта UAH.
- **Фільтри `category` і `member`** — назви без урахування регістру через `str.casefold()`,
  зокрема для кирилиці (так само, як `normalize_category_name`). Невідома назва — помилка зі
  списком наявних.
- **Household** — `SINGLETON_HOUSEHOLD_ID` із `services/access.py`. Порожня база — не помилка.
- **Мова.** Назви інструментів англійською, `title` українською, описи англійською. Описи
  фактичні — що інструмент повертає і в яких одиницях, — без інструкцій щодо поведінки моделі.
- **Кожен інструмент** має `title` і `ToolAnnotations(readOnlyHint=True, openWorldHint=False)`,
  тоді Claude викликає його без підтвердження. Повертає Pydantic-модель.
- **Розбивки** сортуються за сумою за спаданням, при рівності — за назвою. Категорії й учасники
  без витрат у розбивки не потрапляють.
- **Разові витрати (Phase 2 C).** `summarize_spending`, `get_spending_trend` і `list_expenses`
  приймають `one_time: "all" | "exclude" | "only"` (за замовчуванням `"all"` — суми такі самі,
  як до Phase 2). Фільтр — у спільних SQL-умовах разом із датою, категорією й учасником. Поле
  `one_time_amount` — частина `amount` / `total` цього рядка, позначена в боті як «разова»; при
  `one_time: "exclude"` воно завжди 0, при `"only"` дорівнює сумі. Нові поля лише додаються,
  наявні не змінюють значення.

### `get_budget_overview` — «Огляд бюджету»

Вхід: немає.

Вихід:

| Поле | Тип | Зміст |
|---|---|---|
| `today` | date | сьогодні за Києвом |
| `timezone` | str | `"Europe/Kyiv"` |
| `currency` | str | `"UAH"` |
| `members` | list[str] | `display_name` учасників |
| `categories` | list[{`name`, `is_custom`}] | у порядку `list_categories` |
| `first_expense_date`, `last_expense_date` | date \| null | за Києвом; `null`, якщо витрат немає |
| `expense_count` | int | усього записів |

### `summarize_spending` — «Підсумок витрат»

Вхід: `start_date`, `end_date`, `category?`, `member?`.

Вихід: `start_date`, `end_date`, `category` і `member` (канонічні назви з БД або `null`),
`total`, `expense_count`, `by_category: [{name, amount, share_percent, count}]`,
`by_member: [{name, amount, count}]`. `share_percent` — частка від `total`, один знак після коми.

Phase 2 C: вхід + `one_time`; вихід + `one_time` (значення аргументу), `one_time_amount` біля
`total` і в кожному рядку `by_category` та `by_member`.

Приклад (**цифри вигадані**):

```json
{
  "start_date": "2026-09-01", "end_date": "2026-09-14",
  "category": null, "member": null,
  "total": 18450, "expense_count": 143,
  "by_category": [
    {"name": "Їжа", "amount": 9200, "share_percent": 49.9, "count": 88},
    {"name": "Транспорт", "amount": 3100, "share_percent": 16.8, "count": 21}
  ],
  "by_member": [
    {"name": "Serhii", "amount": 10100, "count": 80},
    {"name": "Юля", "amount": 8350, "count": 63}
  ]
}
```

### `get_spending_trend` — «Динаміка витрат»

Вхід: `start_date`, `end_date`, `granularity: "week" | "month"` (за замовчуванням `"month"`),
`split_by: "none" | "category" | "member"` (за замовчуванням `"none"`), `category?`, `member?`.

Кошики:

- Тиждень — Пн–Нд, місяць — календарний, обидва за Києвом.
- Повертаються всі кошики, які перетинає діапазон, зокрема порожні (`total: 0`).
- Межі кошика обрізаються діапазоном; обрізаний кошик має `partial: true`.
- Понад 60 кошиків — помилка з підказкою.
- Групування в Python: витрати діапазону вибираються одним запитом, кошик визначається за
  `to_kyiv(created_at).date()`. SQLite не знає київського літнього часу.

Вихід: `start_date`, `end_date`, `granularity`, `split_by`, `category`, `member`,
`buckets: [{start_date, end_date, partial, total, count, breakdown}]`, де
`breakdown: [{name, amount, count}]`, або `null`, коли `split_by` дорівнює `"none"`.

Phase 2 C: вхід + `one_time`; вихід + `one_time`, `one_time_amount` у кожному кошику й кожному
рядку `breakdown`.

### `list_expenses` — «Список витрат»

Вхід: `start_date`, `end_date`, `category?`, `member?`, `search?: str`, `min_amount?: int` (≥ 0),
`sort: "newest" | "oldest" | "largest"` (за замовчуванням `"newest"`), `limit: int` (за
замовчуванням 50, від 1 до 200), `offset: int` (за замовчуванням 0, ≥ 0).

Відбір і порядок:

- Дата, категорія, учасник і `min_amount` фільтруються в SQL.
- `search` — пошук підрядка в описі через `casefold()` у Python, бо `LOWER()` у SQLite працює
  лише з ASCII. Витрати без опису під `search` не потрапляють.
- Сортування і сторінка застосовуються після `search`, тож `total_count` точний.
- `newest`: `created_at` ↓, `id` ↓. `oldest`: `created_at` ↑, `id` ↑.
  `largest`: `amount` ↓, `created_at` ↓, `id` ↓.

Вихід: `items`, `total_count`, `offset`, `next_offset` (`null` на останній сторінці). Кожен
елемент `items`:

| Поле | Зміст |
|---|---|
| `id` | той самий номер, що «Витрата #N» у боті |
| `datetime` | ISO 8601 із київським зміщенням, напр. `2026-09-14T19:05:00+03:00` |
| `amount` | ціле число гривень |
| `category` | назва категорії |
| `member` | `display_name` автора |
| `description` | текст або `null` |
| `is_one_time` | (Phase 2 C) `true`, якщо в боті позначено «разова» |

Phase 2 C: вхід + `one_time`.

### `get_limit_progress` — «Прогрес лімітів» (Phase 2 C)

Вхід: `date?` — `YYYY-MM-DD`, календарний день за Києвом; за замовчуванням сьогодні. Рік поза
2000–2100 або дата пізніше за сьогодні — помилка.

Що рахує:

- Два періоди, що містять `date`: календарний тиждень (Пн–Нд) і календарний місяць за Києвом —
  у такому порядку: місяць, потім тиждень.
- Момент оцінки `as_of = min(зараз, кінець періоду − 1 мкс)`. Для поточного періоду це «зараз»,
  для минулого — останній момент періоду.
- Ліміти — активні на `as_of` (остання версія з `effective_from ≤ as_of`, не знята). Для
  минулого періоду це ліміт, що діяв на його кінець: ліміт діє на весь період, у якому
  встановлений (рішення підпроєкту A).
- Обчислення — `services.limits.limit_progress(session, household, period_type, as_of)`, тобто
  ті самі `spent`, `percent`, `forecast`, `status`, що показує `/limits`. `spent` — лише
  регулярні витрати (без позначки «разова»).
- Для завершеного періоду `day_index = days_in_period`, тож `forecast = spent`.

Вихід:

| Поле | Зміст |
|---|---|
| `date` | дата запиту |
| `periods` | список з двох елементів, див. нижче |

Кожен елемент `periods`:

| Поле | Зміст |
|---|---|
| `period_type` | `"month"` або `"week"` |
| `start_date`, `end_date` | межі періоду, обидві включно |
| `day_index`, `days_in_period` | день періоду на `as_of` (з 1) і кількість днів |
| `complete` | `true`, якщо період уже закінчився |
| `limits` | список; порожній, якщо лімітів не було |

Кожен елемент `limits` (загальний першим, далі категорії за назвою):

| Поле | Зміст |
|---|---|
| `category` | назва категорії або `null` для загального ліміту |
| `amount` | ліміт, ціле число гривень |
| `spent` | регулярні витрати періоду |
| `percent` | `spent * 100 // amount` |
| `remaining` | `amount − spent`, може бути від'ємним |
| `forecast` | `round(spent / day_index × days_in_period)` |
| `status` | `"over"` при `percent ≥ 100`; `"warn"` при `percent ≥ 80` або `forecast > amount`; інакше `"ok"` |

## Помилки

### Інструменти

| Ситуація | Що отримує модель |
|---|---|
| Дата не у форматі `YYYY-MM-DD` | `start_date must be YYYY-MM-DD, got '…'` |
| Рік поза 2000–2100 | повідомлення з допустимими межами |
| `end_date` раніше за `start_date` | повідомлення з обома датами |
| `limit` поза 1–200, `offset` < 0, `min_amount` < 0 | повідомлення з допустимими межами |
| `get_limit_progress`: `date` пізніше за сьогодні (Phase 2 C) | повідомлення з сьогоднішньою датою за Києвом |
| Понад 60 кошиків | `… yields N weekly buckets (max 60); use granularity="month" or a shorter range` |
| Невідома категорія або учасник | `Unknown category '…'. Known categories: …` (для учасника так само) |
| Два учасники збігаються після `casefold()` | повідомлення, що назва неоднозначна |
| Порожній результат | не помилка: нулі й порожні списки |
| Тип аргументу або значення поза переліком | валідація аргументів SDK за JSON-схемою |
| Непередбачений виняток (баг, заблокована БД) | `Internal error while reading budget data; try again later.` + стек у лозі |

Механіка: валідація і `analytics` кидають `InvalidRequest(ValueError)`. Обгортка інструмента
перетворює його на `ToolError(message)`, а будь-який інший `Exception` логує й перетворює на
`ToolError` із загальним текстом. SDK передає текст `ToolError` моделі як результат із
`isError`.

### HTTP

`401` — гейт (немає токена або він хибний). `421`, `403`, `400` — перевірки SDK (`Host`,
`Origin`, `Content-Type`).

## Конфігурація

| Змінна | За замовчуванням | Призначення |
|---|---|---|
| `MCP_ACCESS_TOKENS` | не задано — конектор вимкнено | `label:token,label:token` |
| `MCP_PUBLIC_HOST` | немає; обов'язкова, коли задано токени | дозволений `Host`: домен Railway або `localhost:8080` локально |
| `PORT` | `8080` | порт uvicorn; Railway підставляє його сам |

Правила вмикання:

- Токенів немає — INFO `Claude connector disabled`, бот працює як раніше.
- Токени задано з помилкою або бракує `MCP_PUBLIC_HOST` — ERROR із причиною (без значень
  токенів), конектор вимкнено, **бот стартує**.
- Тому розбір живе поза валідатором `Settings`: помилка в конфігу конектора не має зупиняти бота.

## Життєвий цикл процесу

```
main():
    settings, engine, bot, dispatcher                  # як зараз
    ro_engine = create_readonly_engine(...)            # лише коли конектор увімкнено
    connector = build_connector(settings, ro_engine)   # None, якщо вимкнено
    mcp_task = create_task(serve_connector(connector)) # якщо увімкнено
    try:
        await bot.set_my_commands(BOT_COMMANDS)
        await dispatcher.start_polling(bot)            # aiogram володіє SIGINT/SIGTERM
    finally:
        if connector:
            connector.server.should_exit = True
            await mcp_task
        await bot.session.close()
        if ro_engine:
            await ro_engine.dispose()
        await engine.dispose()
```

- **Сигнали.** Підклас `uvicorn.Server` з no-op `capture_signals()`. uvicorn 0.53 на старті ставить
  власні обробники через `signal.signal`, а на виході відновлює ті, що бачив на старті. Конектор
  стартує раніше, ніж aiogram реєструє свої обробники (між ними мережевий `set_my_commands`), тож
  після зупинки HTTP для SIGTERM лишається дія за замовчуванням, і повторний SIGTERM під час
  прибирання вбиває процес. Прототип це підтвердив: код виходу −15, engines не закрито. З no-op
  override єдиний власник сигналів — aiogram.
- **Ізоляція збоїв.** `serve_connector` ловить `Exception` **і** `SystemExit`: uvicorn при
  зайнятому порті або збої lifespan викликає `sys.exit(1)`, а `SystemExit` з asyncio-задачі
  зупинив би весь цикл разом із ботом. Лог — ERROR `Claude connector stopped; the bot keeps
  running`. `CancelledError` не ловиться.
- **uvicorn:** `host="0.0.0.0"`, `port=settings.port`, `lifespan="on"`,
  `timeout_graceful_shutdown=5`, `log_config=None`, `access_log=False`, `server_header=False`.
- **SDK:** `streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
  json_response=True, transport_security=…)`. Його lifespan сам запускає session manager, тож
  окремий `session_manager.run()` не потрібен.
- **Порядок зупинки на SIGTERM:** polling → HTTP (дочікується поточних запитів до 5 с) → сесія
  бота → engines. Зупинка бота завершує процес; збій конектора — ні.

## Залежності

- `mcp==2.2.0`; підтягує starlette, uvicorn і httpx2.
- `uvicorn>=0.53,<0.54` явно: override `capture_signals` спирається на внутрішній метод uvicorn.
  Оновлювати лише разом із subprocess-тестом зупинки.
- Вікно pydantic вузьке: aiogram вимагає `<2.14`, mcp — `>=2.12`. Пробне встановлення пройшло
  без конфліктів.
- Нових dev-залежностей немає: `TestClient` зі Starlette 1.6 працює з httpx2, який уже тягне mcp.

## Тестування

Скрізь справжній SQLite-файл у `tmp_path` (схема через `Base.metadata.create_all`, дані — через
engine бота), очікувані значення порахувані вручну, без моків БД.

1. **Інструменти** — через `Client(server)` у процесі, на справжньому read-only engine:
   - межі доби за Києвом: витрата о 23:30 в `end_date` входить, о 00:10 наступного дня — ні;
   - тиждень, що містить перехід на зимовий час (25.10.2026), і обрізані крайові кошики з
     `partial: true`; порожні кошики присутні;
   - `split_by` за категоріями й учасниками;
   - кирилиця без урахування регістру у фільтрах і `search`;
   - `list_expenses`: усі три сортування, `min_amount`, пагінація (`next_offset` на останній
     сторінці — `null`, `total_count` враховує `search`);
   - порожня база: огляд із нулями, підсумок і тренд без помилок;
   - кожна помилка з таблиці вище повертається як `isError` і містить підказку, як виправити
     запит (наприклад, список наявних категорій), а не лише факт помилки;
   - непередбачений виняток дає загальний текст, а в лозі є стек;
   - кожен інструмент оголошує `title` і `readOnlyHint=True`, бо без них Claude питатиме
     підтвердження на кожен виклик;
   - суми `summarize_spending` за період збігаються з `build_report` бота.
   - (Phase 2 C) `one_time`: для кожного з трьох інструментів `all` / `exclude` / `only` дають
     правильні суми, `one_time_amount` і `is_one_time`; за замовчуванням суми не змінились;
   - (Phase 2 C) `get_limit_progress`: поточний період збігається з
     `services.limits.limit_progress`; минулий місяць бере ліміт, чинний на його кінець (зміна
     після кінця місяця не враховується), `complete: true`, `forecast == spent`; разові не
     входять у `spent`; без лімітів — порожні списки; дата в майбутньому — помилка з підказкою;
     інструмент має `title` і `readOnlyHint`.
2. **Read-only engine:** запис падає з `OperationalError`; коміт через engine бота видно в новій
   транзакції читання.
3. **Автентифікація:**
   - розбір `MCP_ACCESS_TOKENS`: валідні пари; окремо кожен некоректний випадок (немає мітки,
     короткий токен, дублікат мітки чи токена);
   - гейт через `TestClient` на повному ASGI-застосунку: без заголовка, з іншою схемою, з хибним
     токеном — `401` без `resource_metadata`; із правильним — `initialize` успішний;
   - `POST /mcp` не редиректиться; чужий `Host` дає `421`;
   - виклик інструмента через HTTP пише в лог мітку токена; значення токена не з'являється в
     жодному записі логу.
4. **Життєвий цикл:**
   - subprocess-тест зі справжнім aiogram `Dispatcher` (фейкова HTTP-сесія замість Telegram) і
     справжнім uvicorn: після SIGTERM процес виходить з кодом 0, лог фіксує порядок polling →
     HTTP → прибирання, а повторний SIGTERM під час прибирання процес не вбиває;
   - зайнятий порт: `serve_connector` завершується без винятку, у лозі ERROR;
   - некоректний конфіг конектора: ERROR у лозі, бот стартує.
5. **Регресія:** наявні тести зелені; тести `parse_custom_range` покривають перехід на
   `kyiv_day_range`.
6. **Вручну після деплою:** `curl` без токена — `401`, з токеном `initialize` — `200`; далі
   питання в claude.ai, звірене з `/report` у боті за той самий період.

## Деплой і підключення

1. **Токени.** Згенерувати локально для кожної людини:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`. У чат не вставляти.
2. **Railway, змінні.** `MCP_ACCESS_TOKENS=serhii:…,yulia:…` — позначити як sealed.
   `MCP_PUBLIC_HOST=${{RAILWAY_PUBLIC_DOMAIN}}`. `PORT` Railway підставляє сам.
3. **Railway, домен.** Networking → Generate Domain. Застосунок слухає один порт, тож Railway
   визначить його автоматично; переконатися, що цільовий порт дорівнює `PORT`.
4. **Деплой.** Автодеплой після merge досі не спрацьовує, тому — через
   `railway service source connect --repo serhii-skotarenko/family-budget --branch main --service family-budget`.
5. **Перевірки.** `dig A <домен>` повертає IPv4-адресу (конектори Claude працюють лише через
   IPv4). Smoke-тест через `curl` (див. «Тестування», п. 6).
6. **claude.ai.** Settings → Connectors → Add custom connector: URL `https://<домен>/mcp`, вхід
   «No sign-in», Request header `Authorization: Bearer <токен>`. Desktop і мобільний
   застосунок підхоплюють конектор з акаунта.
7. **Claude Code.**
   `claude mcp add --transport http family-budget https://<домен>/mcp --header "Authorization: Bearer <токен>"`
   — лише в user scope, щоб токен не потрапив у `.mcp.json` репозиторію.
8. **Ротація токена.** Змінити значення в Railway (запускає редеплой), потім видалити конектор і
   додати знову: налаштування авторизації в конекторі не редагуються.

**Локально:** у `tg-bot/.env` задати `MCP_ACCESS_TOKENS=dev:<32+ символи>` і
`MCP_PUBLIC_HOST=localhost:8080`, запустити `python -m budget_bot` і підключити Claude Code до
`http://localhost:8080/mcp`. У `docker-compose.yml` прокинути порт 8080.

**Документація:** у `tg-bot/README.md` — розділ про конектор (змінні, підключення, ротація) і
нові змінні в розділі «Конфіг»; у `CLAUDE.md` — рядок у «Статусі».

## Перевірити під час деплою

Документація цього не підтверджує, тому перевіряємо на живому сервісі:

- Домен Railway має A-запис IPv4.
- Edge Railway передає `Host` як домен без порту. Інакше буде `421` і в лозі SDK
  `Invalid Host header: …`.
- Чи надсилає бекенд claude.ai заголовок `Origin`, і який саме. Якщо з'явиться `403` і в лозі
  `Invalid Origin header: …` — додати це значення в `allowed_origins`.

## Перевірені факти й джерела

- **mcp 2.2.0** (перевірено в колесі):
  - `/mcp` реєструється як `Route`, не `Mount`;
  - `allowed_hosts` — точний збіг або шаблон `host:*`; запит без `Origin` проходить;
  - автоматичний захист від DNS rebinding вмикається лише для localhost, тож `transport_security`
    передаємо явно;
  - `Client(MCPServer)` підключається в процесі;
  - `ctx.request_context.request` дає доступ до HTTP-запиту;
  - `ToolError` — у `mcp.server.mcpserver.exceptions`;
  - автентифікація через `TokenVerifier` завжди додає `resource_metadata` до `401`.
- **uvicorn 0.53:** `capture_signals()` ставить обробники через `signal.signal` і на виході
  відновлює збережені; при збої прив'язки порту чи lifespan — `sys.exit(STARTUP_FAILURE)`.
  Прототипи 2026-09-15 зі справжнім aiogram: один SIGTERM зупиняє все чисто і без override, а
  повторний SIGTERM під час прибирання без override вбиває процес, з override — ні.
- **Railway:**
  [ліміти](https://docs.railway.com/networking/public-networking/specs-and-limits) — 15 хв на
  запит, поки йдуть дані; 5 хв без даних; 60 с простою HTTP/1.1; 32 KB заголовків.
  [Домени](https://docs.railway.com/networking/domains/working-with-domains) — цільовий порт
  визначається автоматично і редагується.
  [`PORT`](https://docs.railway.com/reference/errors/application-failed-to-respond) —
  підставляється автоматично, слухати `0.0.0.0`.
  [Sealed-змінні](https://docs.railway.com/guides/variables) — значення не видно в UI, API і
  `railway variables`, але воно доступне під час роботи.
- **Конектори Claude:**
  [критерії рев'ю](https://claude.com/docs/connectors/building/review-criteria) — `title`,
  `readOnlyHint`, вузькі описи, зрозумілі помилки;
  [troubleshooting](https://claude.com/docs/connectors/building/troubleshooting) — лише IPv4,
  редиректи відкидають `Authorization`.
