"""Texts of the «💰 Финансы» section."""

from __future__ import annotations

from datetime import date

from babel.dates import format_date

from assistant.core.i18n import Translator, format_day, weekday_short
from assistant.core.models import MoneyCategory, MoneyEntry
from assistant.core.money_style import INCOME
from assistant.core.services.money_cards import month_title
from assistant.core.services.money_month import Alert, Month, share_of
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
        percent = share_of(month.spent, month.budget)  # half up, as the picture and the app
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
        # Half up as everywhere; the 80 % warning never reads «100 %» while something is left.
        "percent": min(share_of(alert.spent, alert.budget), 99),
        "month": month_name(first, t),
        "spent": money(alert.spent, currency, t),
        "budget": money(alert.budget, currency, t),
        "name": f"{alert.category.emoji} {name}" if alert.category is not None else "",
    }
    return t(f"money-alert-{scope}-{alert.threshold}", **values)


def entries_text(
    rows: list[tuple[MoneyEntry, MoneyCategory]],
    first: int,
    total: int,
    today: date,
    names: dict[int, str],
    currency: str,
    t: Translator,
) -> str:
    """A page of this month's entries, numbered from `first`: «3. сб 3 · ☕ Кафе — 250 ₽ · кофе»."""
    if not total:
        return t("money-entries-empty")
    title = month_name(today.replace(day=1), t).capitalize()
    lines = [t("money-entries-title", month=title, count=total), ""]
    for number, (entry, category) in enumerate(rows, start=first):
        what = entry_line(entry, category, names[category.id], currency, entry.day, t)
        day = f"{weekday_short(entry.day.weekday(), t.lang)} {entry.day.day}"
        lines.append(t("money-entries-line", number=number, day=day, what=what))
    return "\n".join(lines)


def _budget_line(label: str, budget: int, spent: int, currency: str, t: Translator) -> str:
    rest = budget - spent
    return t(
        "money-budget-line" if rest >= 0 else "money-budget-line-over",
        label=label,
        budget=money(budget, currency, t),
        spent=money(spent, currency, t),
        rest=money(abs(rest), currency, t),
    )


def budget_text(
    month: Month,
    expenses: list[MoneyCategory],
    names: dict[int, str],
    currency: str,
    t: Translator,
) -> str:
    """The month's budgets: the total one and every category's that has one, cut to Telegram's
    length with the hint kept whole (36 budgets with long names and big sums would pass it)."""
    from assistant.bot.texts import fit  # imported here so that texts can import this module

    lines = [t("money-budget-title", month=month_name(month.first, t)), ""]
    if month.budget is None:
        lines.append(t("money-budget-total-none"))
    else:
        lines.append(_budget_line(t("money-budget-total"), month.budget, month.spent, currency, t))
    spent = {item.category.id: item.amount for item in month.expenses}
    for category in expenses:
        if category.budget is not None:
            label = f"{category.emoji} {names[category.id]}"
            lines.append(
                _budget_line(label, category.budget, spent.get(category.id, 0), currency, t)
            )
    return fit(lines, ["", t("money-budget-hint")])
