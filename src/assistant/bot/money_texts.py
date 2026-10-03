"""Texts of the «💰 Финансы» section."""

from __future__ import annotations

from datetime import date

from babel.dates import format_date

from assistant.core.i18n import Translator, format_day
from assistant.core.models import MoneyCategory, MoneyEntry
from assistant.core.money_style import INCOME
from assistant.core.services.money_cards import month_title
from assistant.core.services.money_month import Alert, Month
from assistant.core.services.money_phrases import format_amount

SHOWN_CATEGORIES = 6


def money(hundredths: int, currency: str, t: Translator, *, plus: bool = False) -> str:
    return format_amount(hundredths, currency, t.lang, plus=plus)


def signed(hundredths: int, currency: str, t: Translator) -> str:
    """A balance: «+12 600 ₽», «−3 000 ₽»."""
    text = money(abs(hundredths), currency, t)
    return f"+{text}" if hundredths >= 0 else f"−{text}"


def bar(share: int) -> str:
    """A share in five cells: 42 % → «▰▰▱▱▱»."""
    filled = min(5, max(0, (share + 10) // 20))
    return "▰" * filled + "▱" * (5 - filled)


def section_text(month: Month, names: dict[int, str], currency: str, t: Translator) -> str:
    """The month so far: spent (of the budget), income and balance, the budget's rest for each
    day left, the largest categories, and how to note an expense."""
    lines = [t("money-title", month=month_title(month.first, t.lang))]
    if month.budget is not None:
        percent = round(100 * month.spent / month.budget)
        lines.append(
            t(
                "money-spent-budget",
                amount=money(month.spent, currency, t),
                budget=money(month.budget, currency, t),
                percent=percent,
            )
        )
    else:
        lines.append(t("money-spent", amount=money(month.spent, currency, t)))
    if month.income:
        lines.append(
            t(
                "money-income",
                amount=money(month.income, currency, t),
                balance=signed(month.balance, currency, t),
            )
        )
    if month.left is not None:
        if month.left < 0:
            lines.append(t("money-over", amount=money(-month.left, currency, t)))
        else:
            lines.append(
                t(
                    "money-left",
                    amount=money(month.left, currency, t),
                    per_day=money(month.per_day or 0, currency, t),
                )
            )
    lines.append("")
    if month.expenses:
        for item in month.expenses[:SHOWN_CATEGORIES]:
            lines.append(
                t(
                    "money-category",
                    bar=bar(item.share),
                    emoji=item.category.emoji,
                    name=names[item.category.id],
                    amount=money(item.amount, currency, t),
                    share=item.share,
                )
            )
    else:
        lines.append(t("money-none"))
    lines += ["", t("money-hint")]
    return "\n".join(lines)


def month_name(first: date, t: Translator) -> str:
    """«октябрь» / «October»: the month alone, as in «бюджет на октябрь»."""
    return str(format_date(first, "LLLL", locale=t.lang))


def day_word(day: date, today: date, t: Translator) -> str:
    """«вчера», «позавчера», «28 сентября»."""
    back = (today - day).days
    if back in (1, 2):
        return t(f"money-day-{back}")
    return format_day(day, t.lang, year=day.year != today.year)


def entry_line(
    entry: MoneyEntry,
    category: MoneyCategory,
    name: str,
    currency: str,
    today: date,
    t: Translator,
) -> str:
    """«☕ Кафе — 250 ₽ · кофе · вчера»; an income has a plus."""
    amount = money(entry.amount, currency, t, plus=category.kind == INCOME)
    parts = [f"{category.emoji} {name} — {amount}"]
    if entry.note:
        parts.append(entry.note)
    if entry.day != today:
        parts.append(day_word(entry.day, today, t))
    return " · ".join(parts)


def entry_text(
    entry: MoneyEntry,
    category: MoneyCategory,
    name: str,
    month: Month,
    currency: str,
    t: Translator,
) -> str:
    """The answer to «кофе 250»: what was noted and the month's spending so far."""
    line = "✅ " + entry_line(entry, category, name, currency, month.today, t)
    title = month_name(month.first, t).capitalize()
    spent = money(month.spent, currency, t)
    if month.budget is not None:
        budget = money(month.budget, currency, t)
        total = t("money-entry-month", month=title, spent=spent, budget=budget)
    else:
        total = t("money-entry-month-plain", month=title, spent=spent)
    return "\n".join((line, total))


def alert_text(alert: Alert, name: str | None, first: date, currency: str, t: Translator) -> str:
    """A budget warning: 80 % reached, or the budget is over."""
    scope = "total" if alert.category is None else "category"
    values = {
        "percent": alert.spent * 100 // alert.budget,
        "month": month_name(first, t),
        "spent": money(alert.spent, currency, t),
        "budget": money(alert.budget, currency, t),
        "name": f"{alert.category.emoji} {name}" if alert.category is not None else "",
    }
    return t(f"money-alert-{scope}-{alert.threshold}", **values)
