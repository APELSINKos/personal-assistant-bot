"""The week's forecast as a picture in the habit card's style (card_kit): the weather now, then up
to seven days, each with its range on the week's scale in the colours of its temperatures.

A 1080×1350 JPEG drawn from the bundled fonts and emoji only, so the same forecast gives the same
picture on any machine; it is drawn in the picture thread, one at a time per process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise

from PIL import Image, ImageDraw

from assistant.core.habit_style import COLORS
from assistant.core.i18n import Translator, format_day, format_day_month, format_weekday
from assistant.core.services import card_kit as kit
from assistant.core.services import weather
from assistant.core.services.card_kit import (
    FOOTER_TOP,
    HEIGHT,
    HINT,
    LEFT,
    PANEL,
    RIGHT,
    TEXT,
    WIDTH,
)
from assistant.core.services.weather import Forecast

SKY = kit.rgb(COLORS["sky"].dark)
# The colour of a temperature on the range bars, from the palette's colours for the dark theme:
# violet frost, sky cold, mint cool, amber warm, coral heat; between two of them it runs smoothly.
STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (-20.0, kit.rgb(COLORS["violet"].dark)),
    (-5.0, SKY),
    (8.0, kit.rgb(COLORS["mint"].dark)),
    (20.0, kit.rgb(COLORS["amber"].dark)),
    (30.0, kit.rgb(COLORS["coral"].dark)),
)
TRACK = (255, 255, 255, 30)  # under a range bar, and between the rows of the days
# A day's row, in x: its name and date end at DAY_RIGHT, then its icon, its lowest ending at
# LOW_RIGHT, the range bar from BAR_LEFT to BAR_RIGHT and its highest ending at HIGH_RIGHT.
DAY_RIGHT, ICON_LEFT, LOW_RIGHT, BAR_LEFT, BAR_RIGHT, HIGH_RIGHT = 342, 358, 548, 572, 852, 972
BAR = 14  # the range bar's height: a day of a single degree is a dot this wide
ROW = 96  # a day's row at most; under a city in two lines the rows are lower


@dataclass(frozen=True)
class DayRow:
    day: date
    code: int  # the day's heaviest weather
    tmin: float
    tmax: float
    chance: int | None  # of rain or snow, percent: the highest of the day's hours


@dataclass(frozen=True)
class ForecastCard:
    city: str
    code: int  # the weather now
    is_day: bool
    temperature: float | None
    feels_like: float | None
    wind: float | None  # m/s
    at: datetime | None  # the time of these values on the place's clock
    today: date  # the place's: «Сегодня» and the footer's date
    days: tuple[DayRow, ...]  # one at least
    bot: str  # the bot's username, without «@»


def card_for(forecast: Forecast, now: datetime, bot: str) -> ForecastCard | None:
    """The picture of `forecast` at the moment `now` (aware): the days of the bot's «📅 Неделя»,
    from the today of the place. None without a day to show."""
    today = weather.local_now(forecast, now).date()
    days = weather.days_from(forecast, today)
    if not days:
        return None
    current = forecast.now
    return ForecastCard(
        city=current.city,
        code=current.code,
        is_day=current.is_day,
        temperature=current.temperature,
        feels_like=current.feels_like,
        wind=current.wind,
        at=current.at,
        today=today,
        days=tuple(DayRow(d.day, d.code, d.tmin, d.tmax, d.precip_chance) for d in days),
        bot=bot,
    )


def degrees(value: float | None) -> str:
    """«+12°», «−3°» with the minus sign, «0°»; «—» without a value. Rounded as the bot's
    «📅 Неделя» rounds them, so the two show the same numbers."""
    if value is None:
        return "—"
    rounded = round(value)
    if rounded == 0:
        return "0°"
    return f"+{rounded}°" if rounded > 0 else f"−{-rounded}°"


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def period(card: ForecastCard, t: Translator) -> str:
    """«Прогноз на 7 дней · 9 октября — 15 октября»; a single day has a single date."""
    dates = format_day(card.days[0].day, t.lang)
    if len(card.days) > 1:
        dates += f" — {format_day(card.days[-1].day, t.lang)}"
    return t("forecast-card-period", count=len(card.days), dates=dates)


def words(card: ForecastCard, t: Translator) -> str:
    """The weather now in words: «Малооблачно»."""
    return _capital(t(weather.describe(card.code, card.is_day)[1]))


def details(card: ForecastCard, t: Translator) -> list[str]:
    """The lines under the words, each when the forecast has its values: «Ощущается как +9°»
    and «Ветер 3 м/с · сейчас 14:30» — «Ветер 3 м/с» without the time, «Сейчас 14:30» without
    the wind. The time is on the place's clock."""
    lines = []
    if card.feels_like is not None:
        lines.append(t("forecast-card-feels", temp=degrees(card.feels_like)))
    wind = None if card.wind is None else t("forecast-card-wind", speed=str(round(card.wind)))
    clock = None if card.at is None else t("forecast-card-now", time=card.at.strftime("%H:%M"))
    known = [part for part in (wind, clock) if part is not None]
    if known:
        lines.append(_capital(" · ".join(known)))
    return lines


def day_name(day: date, today: date, t: Translator) -> str:
    """«Сегодня», «Завтра», then the day of the week: «Воскресенье» / «Sunday»."""
    offset = (day - today).days
    if offset == 0:
        return t("day-today")
    if offset == 1:
        return t("day-tomorrow")
    return _capital(format_weekday(day, t.lang))


def colour_at(temperature: float) -> tuple[int, int, int]:
    """The colour of `temperature` on a range bar: a stop's own at the stop and past the ends, a
    mix of the two stops around it in between."""
    if temperature <= STOPS[0][0]:
        return STOPS[0][1]
    for (low, cold), (high, warm) in pairwise(STOPS):
        if temperature <= high:
            share = (temperature - low) / (high - low)
            return (
                round(cold[0] + (warm[0] - cold[0]) * share),
                round(cold[1] + (warm[1] - cold[1]) * share),
                round(cold[2] + (warm[2] - cold[2]) * share),
            )
    return STOPS[-1][1]


def caption(card: ForecastCard, t: Translator) -> str:
    """«🌤 Москва: погода на неделю»: the photo's caption in the chat, with the icon of now."""
    emoji, _ = weather.describe(card.code, card.is_day)
    return t("forecast-card-caption", emoji=emoji, city=card.city)


def render(card: ForecastCard, t: Translator) -> bytes:
    picture = kit.backdrop().copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    kit.glass(draw, PANEL, 48)
    header_bottom = _header(overlay, draw, card, t)
    now_bottom = _now(draw, card, t, header_bottom + 46)
    _days(overlay, draw, card, t, now_bottom + 56)
    kit.footer(draw, card.bot, card.today, t)
    return kit.jpeg(picture, overlay)


def _header(
    overlay: Image.Image, draw: ImageDraw.ImageDraw, card: ForecastCard, t: Translator
) -> int:
    """The icon of the weather now, the city in up to two lines, the days the picture covers.
    Its bottom."""
    icon, _ = weather.describe(card.code, card.is_day)
    overlay.alpha_composite(kit.emoji_image(icon, 112), (LEFT, 104))
    text_left = LEFT + 140
    size, lines = kit.title_lines(draw, kit.drawable(card.city), RIGHT - text_left)
    y = 100
    for line in lines:
        kit.write(draw, (text_left, y), line, "Manrope", size, 800, TEXT)
        y += round(size * 1.18)
    about = period(card, t)
    about_font = kit.fit(draw, about, "Manrope", 500, range(30, 21, -1), RIGHT - text_left)
    draw.text((text_left + 2, y + 6), about, font=about_font, fill=HINT)
    return max(104 + 112, y + 6 + round(about_font.size))


def _now(draw: ImageDraw.ImageDraw, card: ForecastCard, t: Translator, top: int) -> int:
    """The temperature now, large, and beside it the weather's words over the details: one block
    from the words' capitals to the last baseline, centred on the figure. Its bottom, the
    baselines' rather than the letters', so a tail of «р» moves nothing below."""
    number = degrees(card.temperature)
    number_font = kit.font("Unbounded", 168, 700)
    box = [round(edge) for edge in draw.textbbox((LEFT - 6, top), number, font=number_font)]
    draw.text((LEFT - 6, top), number, font=number_font, fill=TEXT)
    left = box[2] + 36
    said = words(card, t)
    said_font = kit.fit(draw, said, "Manrope", 700, range(48, 31, -2), RIGHT - left)
    lines = [
        (line, kit.fit(draw, line, "Manrope", 500, range(30, 21, -1), RIGHT - left))
        for line in details(card, t)
    ]
    cap = -round(said_font.getbbox("H", anchor="ls")[1])
    baselines = [cap + 46 + 42 * index for index in range(len(lines))]
    height = baselines[-1] if baselines else cap
    y = (box[1] + box[3]) // 2 - height // 2
    draw.text((left, y + cap), said, font=said_font, fill=TEXT, anchor="ls")
    for (line, line_font), baseline in zip(lines, baselines, strict=True):
        draw.text((left, y + baseline), line, font=line_font, fill=HINT, anchor="ls")
    return max(box[3], y + height)


def _days(
    overlay: Image.Image, draw: ImageDraw.ImageDraw, card: ForecastCard, t: Translator, top: int
) -> None:
    """A row a day in one glass block: the day over its date and its chance of rain or snow, its
    icon, its lowest, its piece of the week's range bar and its highest."""
    count = len(card.days)
    row = min(ROW, (FOOTER_TOP - 32 - top) // count)
    kit.glass(draw, (LEFT - 16, top, RIGHT + 16, top + row * count), 32)
    lows = [round(day.tmin) for day in card.days]
    highs = [round(day.tmax) for day in card.days]
    week = (min(lows), max(highs))
    gradient = _gradient(*week)
    name_left = LEFT + 12
    date_font, chance_font = kit.font("Manrope", 24, 500), kit.font("Manrope", 24, 700)
    low_font, high_font = kit.font("Unbounded", 34, 600), kit.font("Unbounded", 34, 700)
    for index, day in enumerate(card.days):
        y = top + index * row
        middle = y + row // 2
        if index:
            draw.line((LEFT + 8, y, RIGHT - 8, y), fill=TRACK, width=2)
        name = day_name(day.day, card.today, t)
        name_font = kit.fit(draw, name, "Manrope", 700, range(34, 25, -1), DAY_RIGHT - name_left)
        draw.text((name_left, middle - 4), name, font=name_font, fill=TEXT, anchor="ls")
        short = format_day_month(day.day, t.lang)
        draw.text((name_left, middle + 28), short, font=date_font, fill=HINT, anchor="ls")
        if day.chance is not None and day.chance >= weather.CHANCE_SHOWN:
            x = name_left + round(draw.textlength(short, font=date_font)) + 12
            overlay.alpha_composite(kit.emoji_image("💧", 22), (x, middle + 8))
            chance = t("forecast-card-chance", chance=day.chance)
            draw.text((x + 26, middle + 28), chance, font=chance_font, fill=SKY, anchor="ls")
        icon, _ = weather.describe(day.code)
        overlay.alpha_composite(kit.emoji_image(icon, 60), (ICON_LEFT, middle - 30))
        low, high = degrees(day.tmin), degrees(day.tmax)
        draw.text((LOW_RIGHT, middle + 12), low, font=low_font, fill=HINT, anchor="rs")
        draw.text((HIGH_RIGHT, middle + 12), high, font=high_font, fill=TEXT, anchor="rs")
        bar_top = middle - BAR // 2
        draw.rounded_rectangle(
            (BAR_LEFT, bar_top, BAR_RIGHT - 1, bar_top + BAR - 1), BAR // 2, fill=TRACK
        )
        start, end = _span(lows[index], highs[index], week)
        mask = Image.new("L", gradient.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (start - BAR_LEFT, 0, end - BAR_LEFT - 1, BAR - 1), BAR // 2, fill=255
        )
        piece = Image.new("RGBA", gradient.size, (0, 0, 0, 0))
        piece.paste(gradient, (0, 0), mask)
        overlay.alpha_composite(piece, (BAR_LEFT, bar_top))


def _gradient(low: int, high: int) -> Image.Image:
    """The week's whole range bar, the week's lowest at its left end and the highest at its
    right: each column in the colour of its own temperature. A day's piece is cut out of it."""
    width = BAR_RIGHT - BAR_LEFT
    line = Image.new("RGBA", (width, 1))
    for x in range(width):
        line.putpixel((x, 0), (*colour_at(low + (high - low) * x / (width - 1)), 255))
    return line.resize((width, BAR), Image.Resampling.NEAREST)


def _span(low: int, high: int, week: tuple[int, int]) -> tuple[int, int]:
    """Where a day's piece of the bar begins and ends, in x: its lowest and highest on the
    week's scale, and never shorter than a dot."""
    width = BAR_RIGHT - BAR_LEFT
    degrees_wide = (week[1] - week[0]) or 1
    start = BAR_LEFT + round(width * (low - week[0]) / degrees_wide)
    end = BAR_LEFT + round(width * (high - week[0]) / degrees_wide)
    if end - start < BAR:
        centre = (start + end) // 2
        start = min(max(centre - BAR // 2, BAR_LEFT), BAR_RIGHT - BAR)
        end = start + BAR
    return start, end


async def draw_card(card: ForecastCard, t: Translator) -> bytes:
    """Draw in the picture thread: about 40 ms of CPU that must not stall the event loop."""
    return await kit.draw_in_thread(render, card, t)
