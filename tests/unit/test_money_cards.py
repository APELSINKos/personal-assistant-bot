from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO

import pytest
from PIL import Image

from assistant.core.clients.cbr import Point
from assistant.core.i18n import translator
from assistant.core.models import MoneyCategory
from assistant.core.money_style import CATEGORY_EMOJI, EXPENSE
from assistant.core.services import money_cards
from assistant.core.services.money_cards import RatesCard, Report, Slice
from assistant.core.services.money_month import CategoryTotal, Month, share_of
from assistant.core.services.money_phrases import format_amount

RU, EN = translator("ru"), translator("en")
NBSP = "\u00a0"
DAYS = tuple([0, 15000, 32000, 48000, 65000, 90000, 140000, 230000] * 4)[:30]
REPORT = Report(
    first=date(2026, 9, 1),
    currency="RUB",
    spent=2435000,
    income=3200000,
    budget=3000000,
    left=565000,
    per_day=None,
    count=87,
    slices=(
        Slice("🛒", "Продукты", 890000, 37),
        Slice("☕", "Кафе", 430000, 18),
        Slice("🚌", "Транспорт", 315000, 13),
        Slice("🏠", "Дом", 280000, 11),
        Slice("📱", "Связь", 120000, 5),
        Slice(None, "", 400000, 16),
    ),
    days=DAYS,
    today=date(2026, 10, 3),
    bot="assistant_bot",
)
USD = (86.9963, 86.8872, 86.5857, 85.4594, 84.3508, 84.2569, 84.1975, 84.4283, 83.2454, 83.4839)
EUR = (100.8287, 100.598, 99.2525, 98.2856, 97.4984, 96.6671, 96.8859, 95.8709, 94.881, 94.3201)
RATES = RatesCard(
    lines=(
        ("USD", tuple(Point(date(2026, 9, 21) + timedelta(days=i), v) for i, v in enumerate(USD))),
        ("EUR", tuple(Point(date(2026, 9, 21) + timedelta(days=i), v) for i, v in enumerate(EUR))),
    ),
    today=date(2026, 10, 3),
    bot="assistant_bot",
)


def picture(jpeg: bytes) -> Image.Image:
    return Image.open(BytesIO(jpeg))


def test_the_report_is_a_1080_by_1350_jpeg_under_a_megabyte() -> None:
    for t in (RU, EN):
        jpeg = money_cards.render_report(REPORT, t)
        assert jpeg[:2] == b"\xff\xd8" and len(jpeg) < 1_000_000
        assert picture(jpeg).size == (1080, 1350)


def test_the_pictures_are_the_same_bytes_on_every_machine() -> None:
    # Windows and Linux alike; a new Pillow or font changes these — then redraw the README report.
    assert (
        hashlib.sha256(money_cards.render_report(REPORT, RU)).hexdigest()
        == "d05afdd35449e8905882f5b79ed938d17309ef9ab611d6af7def65eefee1ddaf"
    )
    assert (
        hashlib.sha256(money_cards.render_report(REPORT, EN)).hexdigest()
        == "5fd37098d0852aa1be39bc3cb6e5786668dff3e3496968f6d316b14ffc4efe5e"
    )
    assert (
        hashlib.sha256(money_cards.render_rates(RATES, RU)).hexdigest()
        == "76d3363281d1a08c942d0a92596b8b5e122867a8f5a99fe7a5f7cf21cbb56342"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"slices": (), "spent": 0, "count": 0, "days": (0,) * 30},  # nothing spent
        {"budget": None, "left": None},  # incomes and the balance instead of the bar
        {"left": -35000},  # over the budget
        {"per_day": 19482},  # this month: what is left for each day
        {"slices": (Slice("💳", "Ж" * 30, 2435000, 100),)},  # a long name, one slice
        {"currency": "AMD", "spent": 99_999_999_999},  # a sign the fonts lack, a huge sum
    ],
)
def test_every_kind_of_month_is_drawn(changes: dict[str, object]) -> None:
    jpeg = money_cards.render_report(replace(REPORT, **changes), RU)  # type: ignore[arg-type]
    assert picture(jpeg).size == (1080, 1350)


def test_every_category_emoji_can_be_drawn() -> None:
    for emoji in CATEGORY_EMOJI:
        slices = (Slice(emoji, "Своя", 1000, 50), Slice(None, "", 1000, 50))
        report = replace(REPORT, slices=slices, spent=2000)
        assert money_cards.render_report(report, EN)[:2] == b"\xff\xd8"


def test_the_rates_picture_and_a_currency_without_data() -> None:
    assert picture(money_cards.render_rates(RATES, EN)).size == (1080, 1350)
    gone = replace(RATES, lines=(("USD", ()), RATES.lines[1]))
    assert picture(money_cards.render_rates(gone, RU)).size == (1080, 1350)


@pytest.mark.parametrize(
    ("currency", "sign"),
    [("RUB", "₽"), ("USD", "$"), ("KZT", "KZT"), ("AMD", "AMD"), ("GEL", "GEL"), ("XXX", "XXX")],
)
def test_a_sign_the_fonts_cannot_draw_becomes_the_code(currency: str, sign: str) -> None:
    assert money_cards.sign_for(currency) == sign
    assert format_amount(25000, currency, "ru", sign=money_cards.sign_for(currency)) == (
        f"250{NBSP}{sign}"
    )


def test_five_largest_categories_and_the_rest_with_the_months_shares() -> None:
    def total(index: int, amount: int) -> CategoryTotal:
        category = MoneyCategory(
            id=index, kind=EXPENSE, emoji=CATEGORY_EMOJI[index], position=index
        )
        return CategoryTotal(category, amount, share_of(amount, 800), None)

    expenses = [total(i, amount) for i, amount in enumerate((300, 200, 100, 100, 50, 25, 25))]
    month = Month(
        first=date(2026, 10, 1), today=date(2026, 10, 3), spent=800, income=0, budget=None,
        left=None, per_day=None, expenses=expenses, incomes=[], days=[0] * 3 + [None] * 28,
        count=7,
    )  # fmt: skip
    names = {i: f"Категория {i}" for i in range(7)}
    report = money_cards.report_for(month, names, "RUB", "assistant_bot")
    # 1 of 8 is 12.5 %: 13 half up, as the bot and the app say, where round() would give 12.
    assert [(item.emoji, item.amount, item.share) for item in report.slices] == [
        (CATEGORY_EMOJI[0], 300, 38), (CATEGORY_EMOJI[1], 200, 25), (CATEGORY_EMOJI[2], 100, 13),
        (CATEGORY_EMOJI[3], 100, 13), (CATEGORY_EMOJI[4], 50, 6), (None, 50, 6),
    ]  # fmt: skip
    assert report.slices[0].name == "Категория 0"


def test_a_share_is_written_as_each_language_writes_it() -> None:
    assert (RU("money-report-share", percent=38), EN("money-report-share", percent=38)) == (
        "38 %", "38%",
    )  # fmt: skip


def test_the_month_title() -> None:
    assert money_cards.month_title(date(2026, 9, 1), "ru") == "Сентябрь 2026"
    assert money_cards.month_title(date(2026, 9, 1), "en") == "September 2026"


async def test_drawing_runs_in_the_picture_thread() -> None:
    assert (await money_cards.draw_report(REPORT, RU))[:2] == b"\xff\xd8"
    assert (await money_cards.draw_rates(RATES, EN))[:2] == b"\xff\xd8"
