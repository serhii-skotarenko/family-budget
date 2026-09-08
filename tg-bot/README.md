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

Бот призначений лише для приватних чатів (див. `docs/requirements.md`) —
вимкніть додавання бота в групи через @BotFather: `/setjoingroups` → Disable.

## Тести і лінт

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/black --check .
```

## Docker

```bash
cp .env.example .env   # заповнити TELEGRAM_BOT_TOKEN і ALLOWED_TELEGRAM_IDS
docker compose up --build
```

Міграції застосовуються автоматично при старті контейнера.

**Не задавайте `DATABASE_PATH` у `.env`, коли деплоїте через Docker/PaaS.**
Образ уже задає `DATABASE_PATH=/data/budget.sqlite3`, що вказує на
змонтований том. `docker-compose.yml` це переживає лише тому, що
`environment:` там пересилює `env_file:`; голий `docker run --env-file .env`
або деплой на PaaS-провайдер (Railway/Fly.io) — саме те, для чого призначений
розділ «Деплой» нижче — цю змінну підхопить і покладе SQLite на файлову
систему контейнера, де її знищить перший же редеплой.

## Деплой

Провайдер — **Railway**. Образ лишається портативним: усе специфічне для
Railway зведене до `railway.json` і налаштувань сервісу, сам Dockerfile
працює будь-де.

### Вимоги, чинні для будь-якої платформи

1. **Persistent volume, змонтований у `/data`** — там лежить `budget.sqlite3`.
   Без тому дані зникнуть при першому ж редеплої.
2. **Змінні середовища:** `TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_IDS`,
   опційно `HOUSEHOLD_NAME`, `RECENT_EXPENSES_LIMIT`. **Не задавайте
   `DATABASE_PATH`** — образ уже вказує ним на змонтований том; перевизначення
   переносить базу на файлову систему контейнера й губить дані при редеплої.
3. **Рівно один інстанс.** Бот працює через long polling; два інстанси на
   одному токені конфліктують за `getUpdates`.
4. **HTTP-порт не потрібен** — це worker-процес, не веб-сервіс.

### Railway: покроково

1. **Створіть проєкт** з цього репозиторію: `New Project` → `Deploy from GitHub repo`.
2. **Service → Settings → Root Directory:** `tg-bot`.
   Це найважливіший крок. Без нього білдер бачить корінь репозиторію, не
   знаходить там Dockerfile, падає назад на автодетект (Railpack) і завершується
   помилкою — у логах буде дерево з `docs/` і `tg-bot/` та `railpack prepare
   exited with an error`.
3. **Створіть том** (`⌘K` → `Create Volume`), прикріпіть до сервісу,
   **Mount path: `/data`**. Каталог не мусить існувати в образі.
4. **Variables** — додайте:
   - `TELEGRAM_BOT_TOKEN` — токен від @BotFather
   - `ALLOWED_TELEGRAM_IDS` — два Telegram ID через кому
   - `HOUSEHOLD_NAME` (опційно)
   - `RECENT_EXPENSES_LIMIT` (опційно)
5. **Deploy.** У логах має зʼявитись `Applying database migrations...`,
   далі `Run polling for bot @…`.

### Чому в Dockerfile немає `VOLUME`

Білдер Railway **відхиляє** директиву `VOLUME`:

```
dockerfile invalid: docker VOLUME at Line 20 is not supported, use Railway Volumes
```

У документації про це не сказано — виявляється лише на невдалому білді. Том
оголошує платформа: у Railway це прикріплений volume із mount path `/data`, а
локально — `budget-data:/data` у `docker-compose.yml`. На персистентність
відсутність директиви не впливає: `VOLUME` створює анонімний том лише тоді,
коли нічого не змонтовано.

### Конфігурація як код

Railway перевів config-as-code (`railway.json` / `railway.toml`) у застарілі:
**нові сервіси його взагалі не читають**, а наявні файли перестануть діяти
2026-12-01. Замість нього — Infrastructure as Code у `.railway/railway.ts`.

Файл у репозиторії згенеровано з фактичного стану проєкту
(`railway config pull`) і доповнено `rootDirectory`. Секретів у ньому немає:
змінні позначені `preserve()`, тобто значення лишаються в Railway.

Щоб ним користуватись, потрібен Node-тулчейн у корені репозиторію:

```bash
npm install railway      # ставить SDK, який імпортує railway.ts
railway config plan      # показує діф із поточним станом
railway config apply     # застосовує
```

**Це поки не перевірено на практиці** — SDK не встановлювали, щоб не тягнути
`node_modules` у Python-репозиторій заради інфраструктурного конфіга. Наразі
сервіс налаштований імперативно (том і змінні — через CLI, Root Directory —
через дашборд). Файл лишено як опис бажаного стану й точка входу, якщо
захочете перейти на IaC повністю.

### Бекап

База — один SQLite-файл на томі, але через WAL-режим поряд з ним живуть
`budget.sqlite3-wal` і `budget.sqlite3-shm`. **Копіювання лише
`budget.sqlite3` може пропустити частину закомічених даних.** Знімайте
узгоджену копію:

```bash
sqlite3 /data/budget.sqlite3 ".backup '/data/backup.sqlite3'"
```

## Конфіг

| Змінна | Обовʼязкова | Значення за замовчуванням | Опис |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | так | — | Токен від @BotFather |
| `ALLOWED_TELEGRAM_IDS` | так | — | Telegram ID через кому |
| `HOUSEHOLD_NAME` | ні | `Сім'я` | Назва домогосподарства |
| `DATABASE_PATH` | ні | `data/budget.sqlite3` | Шлях до файлу SQLite. **У Docker/на PaaS не перевизначайте** — образ задає `/data/budget.sqlite3` (змонтований том); інше значення губить дані при редеплої |
| `RECENT_EXPENSES_LIMIT` | ні | `10` | Скільки записів показує `/list` |
