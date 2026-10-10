"""Draw the forecast picture shown in the README from the showcase world's week.

Usage:  uv run python scripts/forecast_card.py --lang ru --out docs/images/forecast-card.jpg

The weather is made up (scripts/showcase/world.py), the same Moscow week as the bot's «📅 Неделя»
in the README; the rest is the real path: Open-Meteo's answer goes through the parser, the
picture's data and the renderer the bot and the API use, at the moment of the morning digest. The
same arguments always give the same file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from assistant.core.i18n import translator
from assistant.core.services import forecast_cards, weather
from assistant.core.services.forecast_cards import ForecastCard

# Run as a file, Python looks for imports in scripts/ itself; the world is the package
# scripts.showcase, found from the repository's root.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.showcase import world  # noqa: E402

BOT = "ikbo63_24_bot"


def sample_card(lang: str) -> ForecastCard:
    forecast = weather.parse(world.forecast_answer(), world.CITY[lang])
    card = forecast_cards.card_for(forecast, world.DIGEST, BOT)
    assert card is not None, "the showcase week has its days"
    return card


def draw(lang: str) -> bytes:
    return forecast_cards.render(sample_card(lang), translator(lang))


def forecast_alt(lang: str) -> str:
    """The picture's alt text in the README, with the sample's numbers: the weather now and the
    lowest and highest of the week."""
    card, t = sample_card(lang), translator(lang)
    now = f"{forecast_cards.degrees(card.temperature)}, {t(weather.describe(card.code)[1])}"
    low = forecast_cards.degrees(min(day.tmin for day in card.days))
    high = forecast_cards.degrees(max(day.tmax for day in card.days))
    if lang == "ru":
        return (
            f"Прогноз на неделю для Москвы: сейчас {now}; по дням — значок, минимум, полоса "
            f"диапазона и максимум, от {low} до {high}"
        )
    return (
        f"The week's forecast for Moscow: now {now}; for each day an icon, the low, a range bar "
        f"and the high, from {low} to {high}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="ru", choices=("ru", "en"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(draw(args.lang))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
