"""Draw the month report shown in the README from a made-up month.

Usage:  uv run python scripts/money_report.py --lang ru --out docs/images/money-report.jpg

The month is invented; the rest is the real path: the entries go into a throwaway database, the
totals come from the month's rules, the picture from the renderer the bot uses. The same
arguments always give the same file.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.i18n import translator
from assistant.core.models import Base, User
from assistant.core.services import money, money_cards, money_month
from assistant.core.services.money_month import Month

NOW = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)  # a Saturday, noon in Moscow: eight days to go
BUDGET = 3_000_000  # 30 000 ₽, in hundredths
BOT = "ikbo63_24_bot"
# October 2026, in roubles: (day, a preset category, amount).
ENTRIES = (
    (1, "transport", 1500), (1, "phone", 600), (1, "stipend", 3500), (2, "groceries", 1250),
    (3, "cafe", 250), (4, "transport", 640), (5, "groceries", 980), (5, "subscriptions", 510),
    (6, "cafe", 250), (6, "health", 800), (7, "cafe", 450), (8, "groceries", 1430),
    (9, "cafe", 250), (10, "cafe", 1200), (10, "fun", 700), (11, "groceries", 760),
    (12, "transport", 380), (12, "gifts_in", 2000), (13, "cafe", 250), (13, "gifts", 1200),
    (14, "groceries", 1120), (15, "cafe", 450), (15, "phone", 450), (16, "cafe", 250),
    (16, "health", 1350), (17, "groceries", 890), (18, "transport", 520), (19, "fun", 2500),
    (20, "groceries", 1340), (21, "cafe", 450), (22, "cafe", 250), (23, "groceries", 630),
)  # fmt: skip


async def sample_month(lang: str, folder: Path) -> tuple[Month, dict[int, str]]:
    """The month and its categories' names in `lang`."""
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
                money_budget=BUDGET,
            )
            session.add(user)
            await session.flush()
            categories = await money.categories(session, user)
            by_preset = {category.preset: category for category in categories}
            for day, preset, roubles in ENTRIES:
                await money.add_entry(
                    session,
                    user,
                    amount=roubles * 100,
                    category_id=by_preset[preset].id,
                    day=date(2026, 10, day),
                    now=NOW,
                )
            month = await money_month.month(session, user, date(2026, 10, 1), NOW)
            t = translator(lang)
            return month, {category.id: money.name_of(category, t) for category in categories}
    finally:
        await engine.dispose()


async def draw(lang: str) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        month, names = await sample_month(lang, Path(folder))
    report = money_cards.report_for(month, names, "RUB", BOT)
    return money_cards.render_report(report, translator(lang))


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
