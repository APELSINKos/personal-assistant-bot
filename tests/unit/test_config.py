from __future__ import annotations

import pytest
from pydantic import ValidationError

from assistant.core.config import LIMITS, Settings


def test_limits_match_spec() -> None:
    assert (LIMITS.note_length, LIMITS.notes) == (500, 50)
    assert (LIMITS.reminder_length, LIMITS.reminders) == (200, 20)
    assert (LIMITS.habit_length, LIMITS.habits, LIMITS.city_length) == (50, 10, 50)
    assert LIMITS.amount_max == 1_000_000_000
    assert (LIMITS.pinned_notes, LIMITS.note_items, LIMITS.note_item_length) == (5, 20, 100)
    assert (LIMITS.cities, LIMITS.search_length) == (4, 50)


def test_settings_read_token_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "42:abc")
    settings = Settings(_env_file=None)
    assert settings.bot_token.get_secret_value() == "42:abc"
    assert "42:abc" not in repr(settings)
    assert settings.webapp_url is None


@pytest.mark.parametrize("limit", ["0", "-5"])
def test_api_rate_limit_must_allow_requests(monkeypatch, limit) -> None:
    monkeypatch.setenv("API_RATE_LIMIT", limit)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
