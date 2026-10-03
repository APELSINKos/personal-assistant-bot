"""Texts of the «💰 Финансы» section."""

from __future__ import annotations

from assistant.core.i18n import Translator
from assistant.core.services.money_cards import month_title
from assistant.core.services.money_month import Month
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
