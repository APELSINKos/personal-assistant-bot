"""Application settings (environment / .env) and domain limits."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class Limits:
    note_length: int = 500
    notes: int = 50
    reminder_length: int = 200
    reminders: int = 20
    habit_length: int = 50
    habits: int = 10
    city_length: int = 50
    amount_max: float = 1_000_000_000.0
    money_note_length: int = 100
    money_category_length: int = 30
    money_categories: int = 40  # presets included
    money_entries: int = 50_000
    money_entries_month: int = 1_000


LIMITS = Limits()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr
    database_url: str = "sqlite+aiosqlite:///./assistant.db"
    webapp_url: str | None = None
    default_city: str = "Москва"
    default_lat: float = 55.75204
    default_lon: float = 37.61781
    default_timezone: str = "Europe/Moscow"
    default_morning_time: str = "08:00"
    log_level: str = "INFO"
    http_timeout: float = 10.0
    scheduler_interval: float = 20.0
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Requests per minute per user; zero would refuse every request.
    api_rate_limit: int = Field(120, ge=1)
    # The bot builds the MIREA group directory in the background (a full crawl takes about
    # 35 minutes); .env.example turns it off for development.
    mirea_directory: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
