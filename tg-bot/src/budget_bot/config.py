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
