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

Провайдер (Railway / Fly.io) ще не обрано, тому образ навмисно портативний.
Вимоги до будь-якої платформи:

1. **Persistent volume, змонтований у `/data`** — там лежить `budget.sqlite3`.
   Без тому дані зникнуть при першому ж редеплої.
2. **Змінні середовища:** `TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_IDS`,
   опційно `HOUSEHOLD_NAME`, `RECENT_EXPENSES_LIMIT`. **Не задавайте
   `DATABASE_PATH`** — образ уже вказує ним на змонтований том; перевизначення
   переносить базу на файлову систему контейнера й губить дані при редеплої.
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
| `DATABASE_PATH` | ні | `data/budget.sqlite3` | Шлях до файлу SQLite. **У Docker/на PaaS не перевизначайте** — образ задає `/data/budget.sqlite3` (змонтований том); інше значення губить дані при редеплої |
| `RECENT_EXPENSES_LIMIT` | ні | `10` | Скільки записів показує `/list` |
