from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image

from assistant.core.habit_style import COLORS, EMOJI
from assistant.core.i18n import translator
from assistant.core.services import cards, habits

RU, EN = translator("ru"), translator("en")
TODAY = date(2026, 10, 2)  # a Friday
START = date(2025, 9, 29)  # the Monday 52 weeks before this week's
DAYS = 53 * 7
FUTURE = 2  # Saturday and Sunday of this week


def year(cell: str) -> str:
    return cell * (DAYS - FUTURE) + "." * FUTURE


CARD = cards.Card(
    emoji="💪",
    name="Спорт",
    color="mint",
    weekly_goal=7,
    created_on=date(2025, 9, 29),
    streak=42,
    unit="days",
    record=58,
    percent=87,
    week_done=5,
    week_goal=7,
    year_start=START,
    year=year("1"),
    today=TODAY,
    bot="assistant_bot",
)


def picture(jpeg: bytes) -> Image.Image:
    return Image.open(BytesIO(jpeg)).convert("RGB")


def near(pixel: tuple[int, ...], colour: tuple[int, int, int], tolerance: int = 40) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour, strict=True))


def painted(image: Image.Image, colour: tuple[int, int, int]) -> int:
    """Pixels of `colour` in the band of the year map (below the tiles, above the footer)."""
    band = image.crop((96, 820, 984, 1180))
    return sum(1 for pixel in band.get_flattened_data() if near(pixel, colour))


def brightest(image: Image.Image, box: tuple[int, int, int, int]) -> int:
    return max(max(pixel) for pixel in image.crop(box).get_flattened_data())


@pytest.mark.parametrize("t", [RU, EN])
def test_a_card_is_a_1080_by_1350_jpeg_under_a_megabyte(t) -> None:
    jpeg = cards.render(CARD, t)
    assert jpeg[:2] == b"\xff\xd8"
    assert len(jpeg) < 1_000_000
    assert picture(jpeg).size == (1080, 1350)


def test_the_same_habit_gives_the_same_picture() -> None:
    assert cards.render(CARD, RU) == cards.render(CARD, RU)


def test_the_card_is_the_same_bytes_on_every_machine() -> None:
    # Windows and Linux alike; a new Pillow or font changes these — then redraw the README cards.
    assert (
        hashlib.sha256(cards.render(CARD, RU)).hexdigest()
        == "62d5f39d447eaf1f81f74ec9eee2adfe2bb8eae467a68b7540ce27885a42ccf5"
    )
    assert (
        hashlib.sha256(cards.render(CARD, EN)).hexdigest()
        == "b9a1214613327e3de1d344aeb151dd6322d75baffaf93ceb869f0083e7f7e3e7"
    )


def test_the_map_paints_done_days_in_the_habit_colour() -> None:
    mint = (124, 245, 196)
    all_done = picture(cards.render(CARD, RU))
    none_marked = picture(cards.render(replace(CARD, streak=0, year=year("-")), RU))
    # 362 done cells of 13 × 13 against the one legend square
    assert painted(all_done, mint) > 30_000
    assert painted(none_marked, mint) < 1_000


def test_missed_days_are_painted_apart_from_done_ones() -> None:
    missed = picture(cards.render(replace(CARD, streak=0, year=year("0")), RU))
    assert painted(missed, (169, 89, 112)) > 30_000  # the missed red over the dark panel


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "Очень длинное название привычки для проверки"},  # 45 characters, two lines
        {"name": "Ж" * 50},  # one word longer than a line
        {"streak": 9999, "record": 9999, "unit": "weeks", "weekly_goal": 3, "week_goal": 3},
    ],
)
def test_long_names_and_big_numbers_stay_inside_the_content(changes: dict[str, object]) -> None:
    image = picture(cards.render(replace(CARD, **changes), RU))  # type: ignore[arg-type]
    # Text is far brighter than the panel's glass and the backdrop (≤ 85 on a plain card).
    assert brightest(image, (992, 96, 1028, 1250)) < 120  # the panel's right padding
    assert brightest(image, (1036, 0, 1080, 1350)) < 120  # outside the panel


def test_a_name_loses_only_what_its_font_cannot_draw() -> None:
    # A name from before 2.4 may hold an emoji or another script: drawn, they would be boxes.
    assert cards.render(replace(CARD, name="💪 Спорт 读书"), RU) == cards.render(CARD, RU)
    assert cards.render(replace(CARD, name="💪"), RU)[:2] == b"\xff\xd8"  # nothing left: no name


def test_every_emoji_and_colour_of_the_set_can_be_drawn() -> None:
    for emoji, color in zip(EMOJI, list(COLORS) * 4, strict=True):
        assert cards.render(replace(CARD, emoji=emoji, color=color), EN)[:2] == b"\xff\xd8"


def test_caption() -> None:
    assert cards.caption(CARD, RU) == "💪 Спорт — 42 дня подряд"
    assert cards.caption(CARD, EN) == "💪 Спорт — 42 days in a row"
    weekly = replace(CARD, streak=5, unit="weeks")
    assert cards.caption(weekly, RU) == "💪 Спорт — 5 недель подряд"
    assert cards.caption(replace(weekly, streak=1), EN) == "💪 Спорт — 1 week in a row"


def test_the_subtitle_gives_the_first_day_its_year_unless_it_is_this_one() -> None:
    assert cards.subtitle(7, date(2026, 2, 3), TODAY, RU) == "Каждый день · с 3 февраля"
    assert cards.subtitle(3, date(2025, 6, 2), TODAY, RU) == "3 раза в неделю · с 2 июня 2025"
    assert cards.subtitle(1, date(2025, 12, 29), TODAY, EN) == (
        "Once a week · since December 29, 2025"
    )


async def test_drawing_runs_off_the_event_loop() -> None:
    assert (await cards.draw_card(CARD, RU))[:2] == b"\xff\xd8"


async def test_card_for_takes_the_habit_and_its_statistics(session, make_user) -> None:
    user = await make_user()
    monday = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)  # Friday, noon in Moscow
    habit = await habits.create(
        session, user, "Бег", monday, emoji="🏃", color="sky", weekly_goal=2
    )
    for day in (TODAY, TODAY - timedelta(days=1)):
        await habits.set_mark(session, user, habit.id, day, True, now)
    detail = await habits.detail(session, user, habit.id, now)
    card = cards.card_for(detail, TODAY, "assistant_bot")
    assert (card.emoji, card.name, card.color, card.weekly_goal) == ("🏃", "Бег", "sky", 2)
    assert (card.streak, card.unit, card.week_done, card.week_goal) == (1, "weeks", 2, 2)
    assert (card.year_start, card.year, card.bot) == (START, detail.year, "assistant_bot")


def test_the_card_files_are_the_ones_in_the_checksums() -> None:
    listed: dict[str, str] = {}
    for line in (cards.ASSETS / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        listed[name] = digest
    files = {
        path.relative_to(cards.ASSETS).as_posix()
        for path in cards.ASSETS.rglob("*")
        if path.is_file() and path.name not in {"SHA256SUMS", "SOURCES.md"}
    }
    assert files == set(listed)  # every file is listed, and every listed file is there
    for name, digest in listed.items():
        assert hashlib.sha256((cards.ASSETS / name).read_bytes()).hexdigest() == digest, name
