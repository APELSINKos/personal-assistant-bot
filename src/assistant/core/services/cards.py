"""The habit share card: a 1080×1350 JPEG in the app's dark «Вечерний» style.

It is drawn from the bundled fonts and emoji only (assistant/assets, see SOURCES.md), so the same
habit always gives the same picture on any machine. Drawing takes about a tenth of a second and
runs outside the event loop, one card at a time per process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFont

from assistant.core.habit_style import COLORS, DAILY
from assistant.core.i18n import Translator, format_day
from assistant.core.services import card_kit as kit
from assistant.core.services.card_kit import HEIGHT, HINT, LEFT, PANEL, RIGHT, TEXT, WIDTH
from assistant.core.services.habits import DONE, MISSED, OUTSIDE, YEAR_WEEKS, HabitDetail

MISSED_FILL = (255, 122, 144, 150)
UNMARKED_FILL = (255, 255, 255, 34)
OUTSIDE_FILL = (255, 255, 255, 12)
CELL, GAP = 13, 3


@dataclass(frozen=True)
class Card:
    emoji: str
    name: str
    color: str  # a palette key
    weekly_goal: int
    created_on: date
    streak: int
    unit: str  # "days" or "weeks"
    record: int
    percent: int
    week_done: int
    week_goal: int
    year_start: date
    year: str
    today: date
    bot: str  # the bot's username, without "@"


def card_for(detail: HabitDetail, today: date, bot: str) -> Card:
    stats, habit = detail.stats, detail.stats.habit
    return Card(
        emoji=habit.emoji,
        name=habit.name,
        color=habit.color,
        weekly_goal=habit.weekly_goal,
        created_on=habit.created_on,
        streak=stats.streak,
        unit=stats.unit,
        record=stats.record,
        percent=stats.percent,
        week_done=stats.week_done,
        week_goal=stats.week_goal,
        year_start=detail.year_start,
        year=detail.year,
        today=today,
        bot=bot,
    )


def unit_words(count: int, unit: str, t: Translator) -> str:
    return t("card-unit-days" if unit == "days" else "card-unit-weeks", count=count)


def caption(card: Card, t: Translator) -> str:
    """«💪 Спорт — 42 дня подряд»: the photo's caption in the chat."""
    return t(
        "card-caption",
        emoji=card.emoji,
        name=card.name,
        count=card.streak,
        unit=unit_words(card.streak, card.unit, t),
    )


def _name_lines(
    draw: ImageDraw.ImageDraw, name: str, width: float
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in (64, 56, 48):
        font = kit.font("Manrope", size, 800)
        lines = kit.wrap(draw, name, font, width, 2)
        if lines is not None:
            return font, lines
    font = kit.font("Manrope", 48, 800)
    lines = kit.wrap(draw, name, font, width, 99) or [name]
    return font, [lines[0], kit.shorten(draw, " ".join(lines[1:]), font, width)]


def subtitle(weekly_goal: int, created_on: date, today: date, t: Translator) -> str:
    """«Каждый день · с 2 июня»: the goal and the first day — with its year unless it is this one,
    or a habit begun last June would seem to have begun this June."""
    goal = (
        t("card-goal-daily") if weekly_goal == DAILY else t("card-goal-weekly", count=weekly_goal)
    )
    since = format_day(created_on, t.lang, year=created_on.year != today.year)
    return f"{goal} · {t('card-since', date=since)}"


def _cell_fill(state: str, colour: tuple[int, int, int]) -> tuple[int, int, int, int]:
    if state == DONE:
        return (*colour, 255)
    if state == MISSED:
        return MISSED_FILL
    if state == OUTSIDE:
        return OUTSIDE_FILL
    return UNMARKED_FILL


def render(card: Card, t: Translator) -> bytes:
    colour = kit.rgb(COLORS[card.color].dark)
    picture = kit.backdrop().copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    kit.glass(draw, PANEL, 48)

    # Header: the emoji, the name in up to two lines, the goal and the first day.
    overlay.alpha_composite(kit.emoji_image(card.emoji, 112), (LEFT, 104))
    text_left = LEFT + 140
    name_font, lines = _name_lines(draw, kit.drawable(card.name), RIGHT - text_left)
    y = 100
    step = round(name_font.size * 1.18)
    for line in lines:
        draw.text((text_left, y), line, font=name_font, fill=TEXT)
        y += step
    about = subtitle(card.weekly_goal, card.created_on, card.today, t)
    subtitle_font = kit.fit(draw, about, "Manrope", 500, range(30, 21, -1), RIGHT - text_left)
    draw.text((text_left + 2, y + 6), about, font=subtitle_font, fill=HINT)
    header_bottom = max(104 + 112, y + 6 + subtitle_font.size)

    # The streak: a big number, its unit and «подряд» beside it.
    label_font = kit.font("Manrope", 54, 700)
    unit = unit_words(card.streak, card.unit, t)
    in_a_row = t("card-in-a-row")
    label_width = max(
        draw.textlength(unit, font=label_font), draw.textlength(in_a_row, font=label_font)
    )
    number = str(card.streak)
    number_font = kit.fit(
        draw, number, "Unbounded", 700, range(250, 99, -10), RIGHT - LEFT - label_width - 32
    )
    top = header_bottom + 40
    box = tuple(round(edge) for edge in draw.textbbox((LEFT - 8, top), number, font=number_font))
    draw.text((LEFT - 8, top), number, font=number_font, fill=colour)
    label_left = box[2] + 32
    middle = (box[1] + box[3]) // 2
    draw.text((label_left, middle - 70), unit, font=label_font, fill=TEXT)
    draw.text((label_left, middle - 4), in_a_row, font=label_font, fill=TEXT)

    # Three tiles: the record, the past year, this week.
    tiles_top = box[3] + 64
    tiles = (
        (t("card-record"), f"{card.record} {unit_words(card.record, card.unit, t)}"),
        (t("card-year"), f"{card.percent}%"),
        (t("card-week"), t("card-week-value", done=card.week_done, goal=card.week_goal)),
    )
    tile_width = (RIGHT - LEFT - 2 * 24) // 3
    for index, (label, value) in enumerate(tiles):
        x = LEFT + index * (tile_width + 24)
        kit.glass(draw, (x, tiles_top, x + tile_width, tiles_top + 160), 28)
        label_fit = kit.fit(draw, label, "Manrope", 600, range(28, 19, -1), tile_width - 56)
        draw.text((x + 28, tiles_top + 24), label, font=label_fit, fill=HINT)
        value_font = kit.fit(draw, value, "Unbounded", 600, range(44, 23, -2), tile_width - 56)
        draw.text((x + 28, tiles_top + 68), value, font=value_font, fill=TEXT)

    # The last 12 months: one column a week, Monday on top.
    map_title_top = tiles_top + 160 + 76
    draw.text((LEFT, map_title_top), t("card-map"), font=kit.font("Manrope", 32, 700), fill=TEXT)
    pitch = CELL + GAP
    grid_width = YEAR_WEEKS * pitch - GAP
    grid_left = LEFT + (RIGHT - LEFT - grid_width) // 2
    grid_top = map_title_top + 100
    months = t("card-months").split()
    month_font = kit.font("Manrope", 22, 600)
    for column in range(YEAR_WEEKS):
        week_start = card.year_start + timedelta(weeks=column)
        if week_start.day <= 7 and column < YEAR_WEEKS - 2:  # the first week of a month
            draw.text(
                (grid_left + column * pitch, grid_top - 34),
                months[week_start.month - 1],
                font=month_font,
                fill=HINT,
            )
        for row in range(7):
            state = card.year[column * 7 + row]
            x, y = grid_left + column * pitch, grid_top + row * pitch
            draw.rounded_rectangle((x, y, x + CELL, y + CELL), 4, fill=_cell_fill(state, colour))

    legend_top = grid_top + 7 * pitch + 28
    x = LEFT
    for key, fill in (
        ("card-done", (*colour, 255)),
        ("card-missed", MISSED_FILL),
        ("card-unmarked", UNMARKED_FILL),
    ):
        label = t(key)
        draw.rounded_rectangle((x, legend_top + 6, x + 18, legend_top + 24), 4, fill=fill)
        draw.text((x + 30, legend_top), label, font=month_font, fill=HINT)
        x += 30 + round(draw.textlength(label, font=month_font)) + 48

    kit.footer(draw, card.bot, card.today, t)
    return kit.jpeg(picture, overlay)


async def draw_card(card: Card, t: Translator) -> bytes:
    """Draw in the card thread: a tenth of a second of CPU that must not stall the event loop."""
    return await kit.draw_in_thread(render, card, t)
