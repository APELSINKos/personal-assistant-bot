"""The money pictures in the habit card's style (card_kit): the month report and the Bank of
Russia rates over 30 days. Both are 1080×1350 JPEGs drawn in the picture thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from babel.dates import format_date
from PIL import Image, ImageDraw

from assistant.core.clients.cbr import Point
from assistant.core.habit_style import COLORS
from assistant.core.i18n import Translator, format_day, format_day_month, format_number
from assistant.core.money_style import CURRENCIES
from assistant.core.services import card_kit as kit
from assistant.core.services.card_kit import HEIGHT, HINT, LEFT, PANEL, RIGHT, TEXT, WIDTH
from assistant.core.services.money_month import Month, share_of
from assistant.core.services.money_phrases import format_amount

PALETTE = [kit.rgb(COLORS[key].dark) for key in ("mint", "sky", "violet", "rose", "coral")]
REST = kit.rgb(COLORS["slate"].dark)
MINT, AMBER, ROSE, SKY = (kit.rgb(COLORS[key].dark) for key in ("mint", "amber", "rose", "sky"))
TRACK = (255, 255, 255, 30)
SLICES = 5  # the largest categories on the ring; the others are «Остальное»


@dataclass(frozen=True)
class Slice:
    emoji: str | None  # None for «Остальное»
    name: str
    amount: int  # hundredths
    share: int  # percent of the month's expenses, as the bot and the app round it


@dataclass(frozen=True)
class Report:
    first: date  # the month
    currency: str
    spent: int
    income: int
    budget: int | None
    left: int | None
    per_day: int | None
    count: int  # the month's entries
    slices: tuple[Slice, ...]
    days: tuple[int | None, ...]
    today: date
    bot: str  # the bot's username, without «@»


@dataclass(frozen=True)
class RatesCard:
    lines: tuple[tuple[str, tuple[Point, ...]], ...]  # (ISO code, its rates, oldest first)
    today: date
    bot: str


def report_for(month: Month, names: dict[int, str], currency: str, bot: str) -> Report:
    """The picture of a month; `names` maps a category id to its name in the user's language."""
    top = month.expenses[:SLICES]
    slices = [
        Slice(item.category.emoji, names[item.category.id], item.amount, item.share) for item in top
    ]
    rest = sum(item.amount for item in month.expenses[SLICES:])
    if rest:
        slices.append(Slice(None, "", rest, share_of(rest, month.spent)))
    return Report(
        first=month.first,
        currency=currency,
        spent=month.spent,
        income=month.income,
        budget=month.budget,
        left=month.left,
        per_day=month.per_day,
        count=month.count,
        slices=tuple(slices),
        days=tuple(month.days),
        today=month.today,
        bot=bot,
    )


def sign_for(currency: str) -> str:
    """The currency's sign when both fonts can draw it, else its code: «₽», but «AMD». Not from
    the fallback font: its thin «₸» would look foreign among the figures of Unbounded."""
    sign = CURRENCIES[currency].sign if currency in CURRENCIES else currency
    fonts = ("Manrope", "Unbounded")
    return sign if all(kit.has(char, family) for char in sign for family in fonts) else currency


def _money(hundredths: int, report: Report, lang: str) -> str:
    return format_amount(hundredths, report.currency, lang, sign=sign_for(report.currency))


def month_title(first: date, lang: str) -> str:
    """«Сентябрь 2026» / «September 2026»."""
    title = str(format_date(first, "LLLL yyyy", locale=lang))
    return title[:1].upper() + title[1:]


def render_report(report: Report, t: Translator) -> bytes:
    lang = t.lang
    picture = kit.backdrop().copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    kit.glass(draw, PANEL, 48)

    # Header: the bag, the month, what it shows.
    overlay.alpha_composite(kit.emoji_image("💰", 112), (LEFT, 104))
    draw.text(
        (LEFT + 140, 100),
        month_title(report.first, lang),
        font=kit.font("Manrope", 64, 800),
        fill=TEXT,
    )
    draw.text(
        (LEFT + 142, 182), t("money-report-subtitle"), font=kit.font("Manrope", 30, 500), fill=HINT
    )

    # The month's expenses, big.
    total = _money(report.spent, report, lang)
    total_font = kit.fit(draw, total, "Unbounded", 700, range(132, 59, -4), RIGHT - LEFT + 8)
    top = 252
    draw.text((LEFT - 6, top), total, font=total_font, fill=TEXT)

    # The budget: a bar and its words; without one, the incomes and the balance.
    words_font, small = kit.font("Manrope", 30, 600), kit.font("Manrope", 28, 500)
    bar_top = top + 210
    if report.budget is not None and report.left is not None:
        share = report.spent / report.budget
        draw.text(
            (LEFT, bar_top - 46),
            t("money-report-budget", percent=share_of(report.spent, report.budget)),
            font=words_font,
            fill=TEXT,
        )
        of = t("money-report-of", amount=_money(report.budget, report, lang))
        draw.text(
            (RIGHT - draw.textlength(of, font=words_font), bar_top - 46),
            of,
            font=words_font,
            fill=HINT,
        )
        draw.rounded_rectangle((LEFT, bar_top, RIGHT, bar_top + 22), 11, fill=TRACK)
        colour = MINT if share < 0.8 else AMBER if share < 1 else ROSE
        filled = LEFT + round((RIGHT - LEFT) * min(share, 1.0))
        if report.spent > 0:  # a little spending still shows as a dot
            draw.rounded_rectangle(
                (LEFT, bar_top, max(filled, LEFT + 22), bar_top + 22), 11, fill=colour
            )
        if report.left < 0:
            line = t("money-report-over", amount=_money(-report.left, report, lang))
        elif report.per_day is not None:
            line = t(
                "money-report-left-per-day",
                amount=_money(report.left, report, lang),
                per_day=_money(report.per_day, report, lang),
            )
        else:
            line = t("money-report-left", amount=_money(report.left, report, lang))
        draw.text((LEFT, bar_top + 40), line, font=small, fill=HINT)
    else:
        balance = report.income - report.spent
        line = t(
            "money-report-income",
            income=_money(report.income, report, lang),
            balance=("+" if balance >= 0 else "−") + _money(abs(balance), report, lang),
        )
        draw.text((LEFT, bar_top - 20), line, font=words_font, fill=HINT)

    # The ring of the largest categories and its legend.
    ring_top = bar_top + 120
    radius, hole = 176, 112
    centre = (LEFT + radius, ring_top + radius)
    if not report.slices:
        empty_font = kit.font("Manrope", 34, 600)
        draw.text(
            (LEFT, ring_top + radius - 20), t("money-report-empty"), font=empty_font, fill=HINT
        )
    else:
        ring = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring)
        box = (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius)
        start = -90.0
        for index, item in enumerate(report.slices):
            sweep = 360 * item.amount / report.spent
            colour = REST if item.emoji is None else PALETTE[index]
            # The gaps between slices shrink with a thin slice, so its end stays after its start.
            gap = min(1.2, sweep / 4) if len(report.slices) > 1 else 0.0
            ring_draw.pieslice(box, start + gap, start + sweep - gap, fill=(*colour, 255))
            start += sweep
        hole_box = (centre[0] - hole, centre[1] - hole, centre[0] + hole, centre[1] + hole)
        ring_draw.ellipse(hole_box, fill=(0, 0, 0, 0))
        overlay.alpha_composite(ring)
        count_font, word_font = kit.font("Unbounded", 44, 700), kit.font("Manrope", 24, 600)
        count = str(report.count)
        draw.text(
            (centre[0] - draw.textlength(count, font=count_font) / 2, centre[1] - 44),
            count,
            font=count_font,
            fill=TEXT,
        )
        word = t("money-report-entries", count=report.count)
        draw.text(
            (centre[0] - draw.textlength(word, font=word_font) / 2, centre[1] + 14),
            word,
            font=word_font,
            fill=HINT,
        )

        legend_left = LEFT + 2 * radius + 56
        row = 60
        amount_font = kit.font("Manrope", 28, 700)
        share_font = kit.font("Manrope", 24, 600)
        y = ring_top + (2 * radius - len(report.slices) * row) // 2
        for index, item in enumerate(report.slices):
            colour = REST if item.emoji is None else PALETTE[index]
            draw.rounded_rectangle((legend_left, y + 14, legend_left + 14, y + 28), 4, fill=colour)
            name_left = legend_left + 26
            if item.emoji is not None:
                overlay.alpha_composite(kit.emoji_image(item.emoji, 36), (legend_left + 26, y + 3))
                name_left = legend_left + 72
            value = _money(item.amount, report, lang)
            percent = t("money-report-share", percent=item.share)
            value_left = RIGHT - draw.textlength(value, font=amount_font)
            percent_left = value_left - 18 - draw.textlength(percent, font=share_font)
            name = kit.drawable(item.name) if item.emoji is not None else t("money-report-rest")
            room = percent_left - 16 - name_left
            if kit.length(draw, name, "Manrope", 28, 600) > room:
                name = kit.shorten(draw, name, "Manrope", 28, 600, room)
            kit.write(draw, (name_left, y + 4), name, "Manrope", 28, 600, TEXT)
            draw.text((percent_left, y + 8), percent, font=share_font, fill=HINT)
            draw.text((value_left, y + 4), value, font=amount_font, fill=TEXT)
            y += row

    # Day by day.
    days_title = ring_top + 2 * radius + 52
    draw.text(
        (LEFT, days_title), t("money-report-days"), font=kit.font("Manrope", 30, 700), fill=TEXT
    )
    tallest = max((spent or 0 for spent in report.days), default=0)
    bars_top, bars_height = days_title + 56, 104
    pitch = (RIGHT - LEFT) / len(report.days)
    for index, spent in enumerate(report.days):
        x = LEFT + index * pitch
        draw.rounded_rectangle(
            (x + 4, bars_top, x + pitch - 4, bars_top + bars_height), 6, fill=kit.GLASS
        )
        if spent and tallest:
            height = max(8, round(bars_height * spent / tallest))
            draw.rounded_rectangle(
                (x + 4, bars_top + bars_height - height, x + pitch - 4, bars_top + bars_height),
                6,
                fill=SKY,
            )
    marks = kit.font("Manrope", 22, 600)
    for day in (1, 10, 20, len(report.days)):
        text = str(day)
        x = LEFT + (day - 0.5) * pitch - draw.textlength(text, font=marks) / 2
        draw.text((x, bars_top + bars_height + 8), text, font=marks, fill=HINT)

    kit.footer(draw, report.bot, report.today, t)
    return kit.jpeg(picture, overlay)


def render_rates(card: RatesCard, t: Translator) -> bytes:
    lang = t.lang
    picture = kit.backdrop().copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    kit.glass(draw, PANEL, 48)
    overlay.alpha_composite(kit.emoji_image("🏦", 112), (LEFT, 104))
    draw.text(
        (LEFT + 140, 100), t("rates-card-title"), font=kit.font("Manrope", 64, 800), fill=TEXT
    )
    days = [points for _, points in card.lines if points]
    if days:
        first, last = min(p[0].day for p in days), max(p[-1].day for p in days)
        period = t(
            "rates-card-period",
            start=format_day(first, lang),
            end=format_day(last, lang, year=True),
        )
        draw.text((LEFT + 142, 182), period, font=kit.font("Manrope", 30, 500), fill=HINT)
    tiny = kit.font("Manrope", 22, 600)
    for index, (code, points) in enumerate(card.lines):
        top = 262 + index * 470
        kit.glass(draw, (LEFT - 16, top, RIGHT + 16, top + 440), 32)
        title = f"{code} · {t(f'rates-card-name-{code.lower()}')}"
        draw.text((LEFT + 12, top + 26), title, font=kit.font("Manrope", 30, 700), fill=HINT)
        if len(points) < 2:
            draw.text(
                (LEFT + 12, top + 90),
                t("rates-card-unavailable"),
                font=kit.font("Manrope", 34, 600),
                fill=HINT,
            )
            continue
        values = [point.value for point in points]
        last_value = f"{format_number(values[-1], lang)} ₽"
        draw.text((LEFT + 8, top + 66), last_value, font=kit.font("Unbounded", 76, 700), fill=TEXT)
        change = values[-1] - values[0]
        percent = 100 * change / values[0]
        flat = abs(percent) < 0.05  # «0,0 %»: neither up nor down
        colour = HINT if flat else ROSE if change > 0 else MINT
        arrow_x, arrow_y = LEFT + 14, top + 178
        if flat:
            draw.rounded_rectangle(
                (arrow_x, arrow_y + 7, arrow_x + 26, arrow_y + 13), 3, fill=colour
            )
        elif change > 0:
            draw.polygon(
                ((arrow_x, arrow_y + 20), (arrow_x + 26, arrow_y + 20), (arrow_x + 13, arrow_y)),
                fill=colour,
            )
        else:
            draw.polygon(
                ((arrow_x, arrow_y), (arrow_x + 26, arrow_y), (arrow_x + 13, arrow_y + 20)),
                fill=colour,
            )
        delta = t(
            "rates-card-change",
            amount=f"{format_number(abs(change), lang)} ₽",
            percent=("" if flat else "+" if change > 0 else "−")
            + format_number(abs(percent), lang, 1),
        )
        draw.text(
            (arrow_x + 40, arrow_y - 8), delta, font=kit.font("Manrope", 30, 600), fill=colour
        )
        # The line over the period, with its lowest and highest rate.
        chart = (LEFT + 12, top + 240, RIGHT - 12, top + 380)
        low, high = min(values), max(values)
        span = (high - low) or 1.0
        step = (chart[2] - chart[0]) / (len(values) - 1)
        line = [
            (chart[0] + i * step, chart[3] - (value - low) / span * (chart[3] - chart[1]))
            for i, value in enumerate(values)
        ]
        for edge in (chart[1], chart[3]):
            draw.line((chart[0], edge, chart[2], edge), fill=(255, 255, 255, 26), width=2)
        draw.line(line, fill=(*SKY, 255), width=6, joint="curve")
        end = line[-1]
        draw.ellipse((end[0] - 9, end[1] - 9, end[0] + 9, end[1] + 9), fill=(*SKY, 255))
        high_text, low_text = format_number(high, lang), format_number(low, lang)
        # Ending on its highest rate, the line's end dot would touch the label: it steps left.
        high_right = RIGHT - 12 if values[-1] < high else end[0] - 18
        draw.text(
            (high_right - draw.textlength(high_text, font=tiny), chart[1] - 30),
            high_text,
            font=tiny,
            fill=HINT,
        )
        draw.text(
            (RIGHT - 12 - draw.textlength(low_text, font=tiny), chart[3] + 6),
            low_text,
            font=tiny,
            fill=HINT,
        )
        draw.text(
            (chart[0], chart[3] + 6), format_day_month(points[0].day, lang), font=tiny, fill=HINT
        )
    kit.footer(draw, card.bot, card.today, t)
    return kit.jpeg(picture, overlay)


async def draw_report(report: Report, t: Translator) -> bytes:
    return await kit.draw_in_thread(render_report, report, t)


async def draw_rates(card: RatesCard, t: Translator) -> bytes:
    return await kit.draw_in_thread(render_rates, card, t)
