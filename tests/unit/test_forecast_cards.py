from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from assistant.core.habit_style import COLORS, emoji_file
from assistant.core.i18n import translator
from assistant.core.services import card_kit, forecast_cards, weather
from assistant.core.services.forecast_cards import DayRow, ForecastCard
from tests.stubs import FORECAST_NOW, forecast_payload

RU, EN = translator("ru"), translator("en")
TODAY = date(2026, 10, 9)  # a Friday
# (code, lowest, highest, chance): rain and snow, a frosty end, a day of a single degree.
WEEK = (
    (2, 6.0, 13.0, 10),
    (61, 8.0, 12.0, 80),
    (80, 5.0, 9.0, 60),
    (3, 2.0, 7.0, 15),
    (0, -1.0, 6.0, 0),
    (71, -3.0, 1.0, 70),
    (45, 2.6, 3.4, None),
)


def rows(week: tuple[tuple[int, float, float, int | None], ...] = WEEK) -> tuple[DayRow, ...]:
    return tuple(
        DayRow(TODAY + timedelta(days=index), *values) for index, values in enumerate(week)
    )


CARD = ForecastCard(
    city="Москва",
    code=2,
    is_day=True,
    temperature=11.6,
    feels_like=9.2,
    wind=3.4,
    at=datetime(2026, 10, 9, 14, 30),
    today=TODAY,
    days=rows(),
    bot="assistant_bot",
)
FROST = replace(
    CARD,
    code=73,
    is_day=False,
    temperature=-45.2,
    feels_like=-52.4,
    wind=12.3,
    at=datetime(2026, 1, 20, 23, 45),
    days=rows(((73, -48.4, -38.2, 100), (71, -46.0, -41.4, 20)) + ((0, -47.6, -44.5, 0),) * 5),
)
HEAT = replace(
    CARD,
    code=0,
    temperature=48.3,
    feels_like=52.1,
    wind=11.6,
    days=rows(((0, 31.5, 48.4, 0), (95, 30.2, 47.6, 100)) + ((1, 33.8, 46.5, 40),) * 5),
)


def picture(jpeg: bytes) -> Image.Image:
    return Image.open(BytesIO(jpeg)).convert("RGB")


def near(pixel: tuple[int, ...], colour: tuple[int, int, int], tolerance: int = 40) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour, strict=True))


def brightest(image: Image.Image, box: tuple[int, int, int, int]) -> int:
    return max(max(pixel) for pixel in image.crop(box).get_flattened_data())


def painted(image: Image.Image, colour: tuple[int, int, int]) -> int:
    """Pixels of `colour` in the column of the range bars."""
    band = image.crop((572, 300, 852, 1200))
    return sum(1 for pixel in band.get_flattened_data() if near(pixel, colour))


def palette(key: str) -> tuple[int, int, int]:
    return card_kit.rgb(COLORS[key].dark)


def test_degrees_are_rounded_as_in_the_bot_and_written_with_a_true_minus() -> None:
    values = (11.6, -3.4, 0.4, -0.4, 2.5, -2.5, None)
    assert [forecast_cards.degrees(value) for value in values] == [
        "+12°", "−3°", "0°", "0°", "+2°", "−2°", "—",
    ]  # fmt: skip


def test_the_period_counts_the_days_and_gives_their_dates() -> None:
    assert forecast_cards.period(CARD, RU) == "Прогноз на 7 дней · 9 октября — 15 октября"
    assert forecast_cards.period(CARD, EN) == "7-day forecast · October 9 — October 15"
    six, two, one = (replace(CARD, days=CARD.days[:count]) for count in (6, 2, 1))
    assert forecast_cards.period(six, RU) == "Прогноз на 6 дней · 9 октября — 14 октября"
    assert forecast_cards.period(two, RU) == "Прогноз на 2 дня · 9 октября — 10 октября"
    assert forecast_cards.period(one, RU) == "Прогноз на 1 день · 9 октября"
    assert forecast_cards.period(one, EN) == "1-day forecast · October 9"


def test_the_lines_beside_the_temperature_leave_out_what_is_missing() -> None:
    assert forecast_cards.words(CARD, RU) == "Малооблачно"
    assert forecast_cards.words(CARD, EN) == "Partly cloudy"
    assert forecast_cards.details(CARD, RU) == ["Ощущается как +9°", "Ветер 3 м/с · сейчас 14:30"]
    assert forecast_cards.details(CARD, EN) == ["Feels like +9°", "Wind 3 m/s · now 14:30"]
    no_feels = replace(CARD, feels_like=None)
    assert forecast_cards.details(no_feels, RU) == ["Ветер 3 м/с · сейчас 14:30"]
    assert forecast_cards.details(replace(CARD, wind=None), RU) == [
        "Ощущается как +9°", "Сейчас 14:30",
    ]  # fmt: skip
    assert forecast_cards.details(replace(CARD, wind=None), EN) == ["Feels like +9°", "Now 14:30"]
    assert forecast_cards.details(replace(CARD, at=None), RU) == [
        "Ощущается как +9°", "Ветер 3 м/с",
    ]  # fmt: skip
    nothing = replace(CARD, feels_like=None, wind=None, at=None)
    assert forecast_cards.details(nothing, RU) == []


def test_the_days_are_today_tomorrow_then_the_day_of_the_week() -> None:
    names = [forecast_cards.day_name(row.day, TODAY, RU) for row in CARD.days]
    assert names == [
        "Сегодня", "Завтра", "Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг",
    ]  # fmt: skip
    assert [forecast_cards.day_name(row.day, TODAY, EN) for row in CARD.days[:3]] == [
        "Today", "Tomorrow", "Sunday",
    ]  # fmt: skip


def test_the_bars_take_their_colour_from_the_temperature() -> None:
    colour_at = forecast_cards.colour_at
    assert colour_at(-35.0) == colour_at(-20.0) == palette("violet")
    assert colour_at(-5.0) == palette("sky")
    assert colour_at(8.0) == palette("mint")
    assert colour_at(20.0) == palette("amber")
    assert colour_at(30.0) == colour_at(45.0) == palette("coral")
    mint, amber = palette("mint"), palette("amber")
    halfway = tuple(round((a + b) / 2) for a, b in zip(mint, amber, strict=True))
    assert colour_at(14.0) == halfway  # between mint at 8° and amber at 20°


def test_caption() -> None:
    assert forecast_cards.caption(CARD, RU) == "🌤 Москва: погода на неделю"
    assert forecast_cards.caption(CARD, EN) == "🌤 Москва: the week's weather"
    night = replace(CARD, code=1, is_day=False)
    assert forecast_cards.caption(night, RU) == "🌙 Москва: погода на неделю"


def test_card_for_takes_the_week_from_the_forecast() -> None:
    forecast = weather.parse(forecast_payload(), "Москва")  # asked at 10:00 in Moscow
    card = forecast_cards.card_for(forecast, FORECAST_NOW, "assistant_bot")
    assert card is not None
    assert (card.city, card.code, card.is_day, card.bot) == ("Москва", 1, True, "assistant_bot")
    assert (card.temperature, card.feels_like, card.wind) == (9.6, 7.2, 3.4)
    assert (card.at, card.today) == (datetime(2026, 9, 28, 10, 0), date(2026, 9, 28))
    assert [row.day for row in card.days] == [
        date(2026, 9, 28) + timedelta(days=n) for n in range(7)
    ]
    assert card.days[0] == DayRow(date(2026, 9, 28), 1, 5.8, 13.2, 0)


def test_card_for_starts_on_the_today_of_the_place() -> None:
    # At 16:00 UTC it is still the 28th in Moscow, but 02:00 of the 29th in Vladivostok: the
    # forecast kept from the day before starts with the 28th, and the week has six days.
    forecast = weather.parse(forecast_payload(zone="Asia/Vladivostok"), "Владивосток")
    card = forecast_cards.card_for(forecast, datetime(2026, 9, 28, 16, 0, tzinfo=UTC), "bot")
    assert card is not None
    assert card.today == date(2026, 9, 29)
    assert [row.day for row in card.days] == [
        date(2026, 9, 29) + timedelta(days=n) for n in range(6)
    ]


def test_without_a_day_to_show_there_is_no_card() -> None:
    forecast = weather.parse(forecast_payload(), "Москва")
    assert forecast_cards.card_for(replace(forecast, days=[]), FORECAST_NOW, "bot") is None
    week_later = FORECAST_NOW + timedelta(days=8)  # every day of the forecast is past
    assert forecast_cards.card_for(forecast, week_later, "bot") is None


@pytest.mark.parametrize("t", [RU, EN])
def test_a_card_is_a_1080_by_1350_jpeg_under_a_megabyte(t) -> None:
    jpeg = forecast_cards.render(CARD, t)
    assert jpeg[:2] == b"\xff\xd8"
    assert len(jpeg) < 1_000_000
    assert picture(jpeg).size == (1080, 1350)


def test_the_same_forecast_gives_the_same_picture() -> None:
    assert forecast_cards.render(CARD, RU) == forecast_cards.render(CARD, RU)


def test_the_card_is_the_same_bytes_on_every_machine() -> None:
    # Windows and Linux alike; a new Pillow or font changes these — then redraw the README pictures.
    assert (
        hashlib.sha256(forecast_cards.render(CARD, RU)).hexdigest()
        == "a7669545e6f15bf11a59cc20c2dad6cfa85c67dc1418b988ed4fb77a93038959"
    )
    assert (
        hashlib.sha256(forecast_cards.render(CARD, EN)).hexdigest()
        == "edc06fb7d0a76085202af08fbc8e9c17228d6a27410027683eb7ed9ebce07123"
    )


def test_kazakh_letters_of_a_city_are_drawn() -> None:
    # Manrope lacks «Қ» and «ғ»: the fallback font draws them, on the line of the others.
    kazakh = forecast_cards.render(replace(CARD, city="Қарағанды"), RU)
    dropped = forecast_cards.render(replace(CARD, city="араанды"), RU)  # without those letters
    assert kazakh != dropped
    assert (
        hashlib.sha256(kazakh).hexdigest()
        == "8e44712ab5a2dd6c46f913e5bdd8ba741f69735afb4cb83425cc319e9dbd106f"
    )
    image = picture(kazakh)
    # The capital «Қ» rises above the small letters, where «араанды» has only the backdrop.
    capitals = (236, 124, 290, 131)
    assert brightest(image, capitals) > 200
    assert brightest(picture(dropped), capitals) < 160
    assert brightest(image, (992, 96, 1028, 1250)) < 120  # the panel's right padding
    assert brightest(image, (1036, 0, 1080, 1350)) < 120  # outside the panel


@pytest.mark.parametrize("card", [FROST, HEAT], ids=["frost", "heat"])
def test_frost_and_heat_stay_inside_their_columns(card: ForecastCard) -> None:
    image = picture(forecast_cards.render(card, RU))
    # Text is far brighter than the glass and the backdrop (≤ 85 on a plain card).
    assert brightest(image, (992, 96, 1028, 1250)) < 120  # the panel's right padding
    assert brightest(image, (1036, 0, 1080, 1350)) < 120  # outside the panel
    days = (480, 1180)  # the rows of the days, whatever the header
    assert brightest(image, (346, days[0], 356, days[1])) < 120  # the day | the icon
    assert brightest(image, (552, days[0], 568, days[1])) < 120  # the lowest | the bar
    assert brightest(image, (856, days[0], 862, days[1])) < 120  # the bar | the highest


def test_frost_paints_the_bars_violet_and_heat_coral() -> None:
    frosty = picture(forecast_cards.render(FROST, RU))
    hot = picture(forecast_cards.render(HEAT, RU))
    assert painted(frosty, palette("violet")) > 5_000
    assert painted(frosty, palette("coral")) < 100
    assert painted(hot, palette("coral")) > 5_000
    assert painted(hot, palette("violet")) < 100


def test_a_chance_of_rain_or_snow_shows_from_twenty_percent() -> None:
    def drawn(chance: int | None) -> bytes:
        days = rows(((61, 8.0, 12.0, chance), *WEEK[1:]))
        return forecast_cards.render(replace(CARD, days=days), RU)

    assert drawn(19) == drawn(0) == drawn(None)
    assert drawn(20) != drawn(19)


@pytest.mark.parametrize("count", [6, 1])
def test_six_days_and_one_day(count: int) -> None:
    image = picture(forecast_cards.render(replace(CARD, days=CARD.days[:count]), RU))
    assert image.size == (1080, 1350)
    assert brightest(image, (992, 96, 1028, 1250)) < 120


@pytest.mark.parametrize(
    ("city", "size"),
    [
        ("Новоалександровск Ставропольский", 64),  # the tallest header: two lines at 64 px
        ("Новоалександровск Ставропольского края и ещё длиннее название", 48),
    ],
    ids=["two-lines", "ellipsis"],
)
def test_a_city_in_two_lines_ends_in_an_ellipsis_if_too_long_and_the_days_still_fit(
    city: str, size: int
) -> None:
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    found, lines = card_kit.title_lines(draw, city, 748)  # beside the 112-px icon
    assert (found, len(lines)) == (size, 2)
    assert lines[1].endswith("…") == (size == 48)
    image = picture(forecast_cards.render(replace(CARD, city=city), RU))
    assert brightest(image, (992, 96, 1028, 1250)) < 120  # the panel's right padding
    assert brightest(image, (96, 1194, 984, 1220)) < 120  # between the days and the footer
    assert brightest(image, (96, 1226, 360, 1260)) > 200  # the footer is there


def test_every_icon_the_weather_shows_has_its_picture() -> None:
    icons = {weather.describe(code, day)[0] for code in range(-1, 101) for day in (True, False)}
    assert len(icons) == 10  # eight kinds of weather, the moon at night and «нет данных»
    for icon in icons:
        assert (card_kit.ASSETS / "emoji" / emoji_file(icon)).is_file(), icon


async def test_drawing_runs_off_the_event_loop() -> None:
    assert (await forecast_cards.draw_card(CARD, RU))[:2] == b"\xff\xd8"
