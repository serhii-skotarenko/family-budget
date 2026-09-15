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
    assert settings.port_raw == "9000"


def test_connector_settings_are_optional():
    settings = make_settings()
    assert (settings.mcp_access_tokens_raw, settings.mcp_public_host, settings.port_raw) == (
        None,
        None,
        None,
    )


def test_a_non_numeric_port_does_not_stop_settings_from_loading():
    settings = make_settings(PORT="abc")
    assert settings.port_raw == "abc"
