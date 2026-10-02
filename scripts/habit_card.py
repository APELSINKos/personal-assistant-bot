"""Draw the habit card shown in the README from a made-up habit.

Usage:  uv run python scripts/habit_card.py --lang ru --out docs/images/habit-card.jpg

The habit and its year of marks are invented; the rest is the real path: the marks go into a
throwaway database, the numbers come from the habit rules, the picture from the renderer the bot
and the API use. The same arguments always give the same file.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.i18n import translator
from assistant.core.models import Base, HabitMark, User
from assistant.core.services import cards, habits
from assistant.core.services.habits import HabitDetail

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)  # a Friday, noon in Moscow
BEGAN = datetime(2025, 6, 2, 9, 0, tzinfo=UTC)
STREAK = 42  # the last 42 days, today included
RECORD = (date(2026, 3, 2), date(2026, 4, 28))  # 58 days in a row
NAMES = {"ru": "Тренировка", "en": "Workout"}
BOT = "ikbo63_24_bot"
ONE_DAY = timedelta(days=1)


def made_up_marks(began: date, today: date) -> dict[date, bool]:
    """Mostly done, sometimes missed or left unmarked; a record run in spring and the streak."""
    pick = random.Random(2026)  # the same year on every run
    runs = [RECORD, (today - (STREAK - 1) * ONE_DAY, today)]
    marks: dict[date, bool] = {}
    day = began
    while day <= today:
        if any(first <= day <= last for first, last in runs):
            marks[day] = True
        elif any(day in (first - ONE_DAY, last + ONE_DAY) for first, last in runs):
            marks[day] = False  # a missed day on each side keeps a run exactly as long
        else:
            roll = pick.random()
            if roll < 0.8:
                marks[day] = True
            elif roll < 0.92:
                marks[day] = False
            # else: left unmarked
        day += ONE_DAY
    return marks


async def sample_detail(lang: str, folder: Path) -> HabitDetail:
    engine = create_engine(f"sqlite+aiosqlite:///{(folder / 'sample.db').as_posix()}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with make_sessionmaker(engine)() as session:
            user = User(
                id=1,
                first_name="Demo",
                tg_language=lang,
                city="Москва",
                lat=55.75,
                lon=37.62,
                timezone="Europe/Moscow",
            )
            session.add(user)
            await session.flush()
            habit = await habits.create(session, user, NAMES[lang], BEGAN, emoji="💪")
            today = NOW.date()
            session.add_all(
                HabitMark(habit_id=habit.id, day=day, done=done)
                for day, done in made_up_marks(habit.created_on, today).items()
            )
            await session.flush()
            return await habits.detail(session, user, habit.id, NOW)
    finally:
        await engine.dispose()


async def draw(lang: str) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        detail = await sample_detail(lang, Path(folder))
    return cards.render(cards.card_for(detail, NOW.date(), BOT), translator(lang))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="ru", choices=("ru", "en"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(asyncio.run(draw(args.lang)))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
