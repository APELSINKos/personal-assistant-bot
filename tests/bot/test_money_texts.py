from __future__ import annotations

from datetime import date

from assistant.bot.money_texts import alert_text, section_text
from assistant.core.i18n import translator
from assistant.core.services.money_month import Alert, Month

RU = translator("ru")


def month(spent: int, budget: int) -> Month:
    return Month(
        first=date(2026, 10, 1), today=date(2026, 10, 3), spent=spent, income=0, budget=budget,
        left=budget - spent, per_day=None, expenses=[], incomes=[], days=[0, 0, 0] + [None] * 28,
        count=1,
    )  # fmt: skip


def test_the_budgets_percent_is_rounded_half_up() -> None:
    # 1 000 of 8 000 is 12.5 %: 13, as the picture and the app say, where round() gives 12.
    assert "(13 %)" in section_text(month(100000, 800000), {}, "RUB", RU)


def test_the_80_percent_warning_never_reads_100() -> None:
    alert = Alert(category=None, threshold=80, spent=2988000, budget=3000000)  # 99.6 %
    text = alert_text(alert, None, date(2026, 10, 1), "RUB", RU)
    assert text.startswith("⚠️ Потрачено 99 % бюджета на октябрь")
