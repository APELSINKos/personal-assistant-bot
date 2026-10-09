from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path

from scripts.forecast_card import draw, forecast_alt, sample_card
from scripts.showcase import world

from assistant.core.clients.openmeteo import check_forecast

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"


def test_the_readme_week_is_the_showcase_world_s() -> None:
    answer = world.forecast_answer()
    assert check_forecast(answer) is answer  # an answer the client would keep
    card = sample_card("ru")
    assert (card.city, card.at) == ("Москва", datetime(2026, 10, 7, 8, 0))  # the morning digest
    assert card.today == date(2026, 10, 7)
    assert sample_card("en").city == "Moscow"
    # The week of the README's «📅 Неделя»: rain tonight, a sunny Saturday, the first wet snow.
    days = [
        (row.day.day, row.code, round(row.tmin), round(row.tmax), row.chance) for row in card.days
    ]
    assert days == [
        (7, 61, 5, 13, 80), (8, 3, 5, 11, 20), (9, 2, 3, 12, 10), (10, 0, 2, 12, 0),
        (11, 53, 6, 10, 70), (12, 45, 4, 8, 15), (13, 71, -1, 3, 60),
    ]  # fmt: skip


def test_the_alt_text_gives_the_sample_s_numbers() -> None:
    assert forecast_alt("ru") == (
        "Прогноз на неделю для Москвы: сейчас +6°, пасмурно; по дням — значок, минимум, "
        "полоса диапазона и максимум, от −1° до +13°"
    )
    assert forecast_alt("en") == (
        "The week's forecast for Moscow: now +6°, overcast; for each day an icon, the low, "
        "a range bar and the high, from −1° to +13°"
    )


def test_the_readmes_show_the_sample_with_its_alt_text() -> None:
    for lang, readme, name in (
        ("ru", "README.md", "forecast-card.jpg"),
        ("en", "README.en.md", "forecast-card.en.jpg"),
    ):
        text = (ROOT / readme).read_text(encoding="utf-8")
        assert f'<img src="docs/images/{name}" width="360" alt="{forecast_alt(lang)}">' in text


def test_the_readme_forecasts_are_what_the_script_draws() -> None:
    # A change to the picture, its fonts or the weather's rules lands here: redraw them with
    # scripts/forecast_card.py and update the sums in test_forecast_cards.py.
    for lang, name in (("ru", "forecast-card.jpg"), ("en", "forecast-card.en.jpg")):
        drawn = hashlib.sha256(draw(lang)).hexdigest()
        assert drawn == hashlib.sha256((IMAGES / name).read_bytes()).hexdigest(), name
