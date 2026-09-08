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
