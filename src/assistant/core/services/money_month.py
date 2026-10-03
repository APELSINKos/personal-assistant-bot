"""A month of money: what was spent and received, by category and by day, the budget's rest, and
the budget warnings an expense sets off.

The month is a calendar month of the user's local dates. Shares are whole percent of the month's
expenses (they need not add up to exactly 100).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.models import MoneyAlert, MoneyCategory, MoneyEntry, User
from assistant.core.money_style import EXPENSE, INCOME
from assistant.core.services import money
from assistant.core.timeutil import local_today

THRESHOLDS = (80, 100)  # percent of a budget


@dataclass(frozen=True)
class CategoryTotal:
    category: MoneyCategory
    amount: int  # spent (an expense category) or received (an income one) this month
    share: int  # percent of the month's expenses; 0 for incomes
    left: int | None  # the category's budget minus its expenses; None without a budget


@dataclass(frozen=True)
class Month:
    first: date
    today: date  # the user's local today
    spent: int
    income: int
    budget: int | None
    left: int | None  # budget − spent: negative when over; None without a budget
    per_day: int | None  # what is left for each day to the month's end; this month, if any left
    expenses: list[CategoryTotal]  # the largest first
    incomes: list[CategoryTotal]
    days: list[int | None]  # spent on each day of the month; None for the days still ahead
    count: int  # entries this month

    @property
    def balance(self) -> int:
        return self.income - self.spent


@dataclass(frozen=True)
class Alert:
    category: MoneyCategory | None  # None: the budget of all expenses
    threshold: int
    spent: int
    budget: int


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month(first: date) -> date:
    return (first + timedelta(days=32)).replace(day=1)


def share_of(part: int, whole: int) -> int:
    """`part` in percent of `whole`, half a percent up (12.5 → 13): the shares the bot, the app and
    the month's picture all show."""
    return (200 * part + whole) // (2 * whole) if whole else 0


async def entries(
    session: AsyncSession, user: User, first: date, *, category_id: int | None = None
) -> list[tuple[MoneyEntry, MoneyCategory]]:
    """The month's entries with their categories, the newest first."""
    query = (
        select(MoneyEntry, MoneyCategory)
        .join(MoneyCategory, MoneyEntry.category_id == MoneyCategory.id)
        .where(
            MoneyEntry.user_id == user.id,
            MoneyEntry.day >= first,
            MoneyEntry.day < next_month(first),
        )
        .order_by(MoneyEntry.day.desc(), MoneyEntry.id.desc())
    )
    if category_id is not None:
        query = query.where(MoneyEntry.category_id == category_id)
    return [(row[0], row[1]) for row in await session.execute(query)]


async def first_month(session: AsyncSession, user: User) -> date | None:
    """The month of the user's oldest entry."""
    oldest = await session.scalar(
        select(func.min(MoneyEntry.day)).where(MoneyEntry.user_id == user.id)
    )
    return None if oldest is None else month_start(oldest)


async def month(
    session: AsyncSession, user: User, first: date | None = None, now: datetime | None = None
) -> Month:
    today = local_today(user.timezone, now)
    start = month_start(first or today)
    rows = await entries(session, user, start)
    by_category: dict[int, int] = defaultdict(int)
    by_day: dict[date, int] = defaultdict(int)
    spent = received = 0
    for entry, category in rows:
        by_category[category.id] += entry.amount
        if category.kind == EXPENSE:
            spent += entry.amount
            by_day[entry.day] += entry.amount
        else:
            received += entry.amount
    known = {category.id: category for _, category in rows}

    def totals(kind: str) -> list[CategoryTotal]:
        found = []
        for category_id, amount in by_category.items():
            category = known[category_id]
            if category.kind != kind:
                continue
            left = None if category.budget is None else category.budget - amount
            share = share_of(amount, spent) if kind == EXPENSE else 0
            found.append(CategoryTotal(category, amount, share, left))
        return sorted(found, key=lambda item: (-item.amount, item.category.position))

    length = calendar.monthrange(start.year, start.month)[1]
    days: list[int | None] = []
    for offset in range(length):
        day = start + timedelta(days=offset)
        days.append(by_day.get(day, 0) if day <= today else None)
    budget = user.money_budget
    left = None if budget is None else budget - spent
    per_day = None
    if left is not None and left > 0 and start == month_start(today):
        per_day = left // ((next_month(start) - today).days)
    return Month(
        first=start,
        today=today,
        spent=spent,
        income=received,
        budget=budget,
        left=left,
        per_day=per_day,
        expenses=totals(EXPENSE),
        incomes=totals(INCOME),
        days=days,
        count=len(rows),
    )


async def _spent(session: AsyncSession, user: User, first: date, category_id: int | None) -> int:
    query = (
        select(func.coalesce(func.sum(MoneyEntry.amount), 0))
        .join(MoneyCategory, MoneyEntry.category_id == MoneyCategory.id)
        .where(
            MoneyEntry.user_id == user.id,
            MoneyCategory.kind == EXPENSE,
            MoneyEntry.day >= first,
            MoneyEntry.day < next_month(first),
        )
    )
    if category_id is not None:
        query = query.where(MoneyEntry.category_id == category_id)
    return int(await session.scalar(query) or 0)


async def alerts_after(
    session: AsyncSession, user: User, entry: MoneyEntry, now: datetime | None = None
) -> list[Alert]:
    """The warnings an expense of this month sets off: for its category's budget and for the
    budget of all expenses, a threshold reached for the first time this month. Both
    thresholds may be reached at once; then only the higher one is shown (both are kept)."""
    first = month_start(local_today(user.timezone, now))
    category = await money.category(session, user, entry.category_id)
    if category.kind != EXPENSE or month_start(entry.day) != first:
        return []
    key = first.strftime("%Y-%m")
    found: list[Alert] = []
    for scope, budget in ((category, category.budget), (None, user.money_budget)):
        if budget is None:
            continue
        spent = await _spent(session, user, first, None if scope is None else scope.id)
        fresh = []
        for threshold in THRESHOLDS:
            if spent * 100 < budget * threshold:
                continue
            ident = (user.id, key, 0 if scope is None else scope.id, threshold)
            if await session.get(MoneyAlert, ident) is None:
                session.add(
                    MoneyAlert(
                        user_id=user.id, month=key, category_id=ident[2], threshold=threshold
                    )
                )
                fresh.append(threshold)
        if fresh:
            found.append(Alert(category=scope, threshold=max(fresh), spent=spent, budget=budget))
    await session.flush()
    return found
