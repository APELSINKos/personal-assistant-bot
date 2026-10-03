"""Money: a user's categories (the presets and their own), entries, the notes they moved to
another category, budgets and currency.

Amounts are hundredths of the user's currency (an int); days are the user's local dates. A
category's kind (expense or income) is the kind of every entry in it.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.i18n import Translator, labels
from assistant.core.models import MoneyCategory, MoneyEntry, MoneyWord, User
from assistant.core.money_style import (
    CATEGORY_EMOJI,
    CURRENCIES,
    EXPENSE,
    INCOME,
    KINDS,
    OTHER,
    PRESETS,
)
from assistant.core.services.money_phrases import Quick, dictionary_guess, note_key
from assistant.core.timeutil import local_today, utcnow

MAX_HUNDREDTHS = int(LIMITS.amount_max) * 100
OLDEST_DAY = 366  # an entry may be dated up to this many days back
KEEP = object()  # «do not change» for a field that can also be cleared with None


def name_of(category: MoneyCategory, t: Translator) -> str:
    """A preset is named by its translation until the user renames it."""
    return category.name or t(f"money-cat-{category.preset}")


async def _categories(session: AsyncSession, user_id: int) -> list[MoneyCategory]:
    rows = await session.scalars(
        select(MoneyCategory)
        .where(MoneyCategory.user_id == user_id)
        .order_by(MoneyCategory.position, MoneyCategory.id)
    )
    return list(rows)


async def categories(
    session: AsyncSession, user: User, *, kind: str | None = None, visible: bool = False
) -> list[MoneyCategory]:
    """The user's categories in their order; the presets are created on the first call."""
    found = await _categories(session, user.id)
    if not found:
        # ON CONFLICT: the bot and the API may create them at the same moment.
        await session.execute(
            sqlite_insert(MoneyCategory)
            .values(
                [
                    {
                        "user_id": user.id,
                        "kind": preset.kind,
                        "preset": preset.key,
                        "emoji": preset.emoji,
                        "hidden": False,
                        "position": position,
                        "created_at": utcnow(),
                    }
                    for position, preset in enumerate(PRESETS)
                ]
            )
            .on_conflict_do_nothing(index_elements=["user_id", "preset"])
        )
        found = await _categories(session, user.id)
    return [
        category
        for category in found
        if (kind is None or category.kind == kind) and not (visible and category.hidden)
    ]


async def category(session: AsyncSession, user: User, category_id: int) -> MoneyCategory:
    found = await session.scalar(
        select(MoneyCategory).where(
            MoneyCategory.id == category_id, MoneyCategory.user_id == user.id
        )
    )
    if found is None:
        raise NotFound(entity="category")
    return found


def _clean_text(text: str, limit: int, field: str) -> str:
    cleaned = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", text).split())
    if len(cleaned) > limit:
        raise InvalidInput(field=field, reason="length", limit=limit)
    return cleaned


def _same(a: str, b: str) -> bool:
    return a.casefold().replace("ё", "е") == b.casefold().replace("ё", "е")


async def _check_name(
    session: AsyncSession, user: User, kind: str, name: str, own_id: int | None = None
) -> str:
    cleaned = _clean_text(name, LIMITS.money_category_length, "name")
    if not cleaned:
        raise InvalidInput(field="name", reason="empty")
    for other in await categories(session, user, kind=kind):
        if other.id == own_id:
            continue
        names = {other.name} if other.name else labels(f"money-cat-{other.preset}")
        if any(_same(cleaned, known) for known in names):
            raise InvalidInput(field="name", reason="duplicate")
    return cleaned


def _check_amount(amount: int, field: str = "amount") -> int:
    if not 0 < amount <= MAX_HUNDREDTHS:
        raise InvalidInput(field=field, reason="out_of_range")
    return amount


async def create_category(
    session: AsyncSession, user: User, kind: str, name: str, emoji: str
) -> MoneyCategory:
    if kind not in KINDS:
        raise InvalidInput(field="kind", reason="unknown")
    if emoji not in CATEGORY_EMOJI:
        raise InvalidInput(field="emoji", reason="not_in_set")
    existing = await categories(session, user)
    if len(existing) >= LIMITS.money_categories:
        raise LimitReached(entity="category", limit=LIMITS.money_categories)
    cleaned = await _check_name(session, user, kind, name)
    created = MoneyCategory(
        user_id=user.id,
        kind=kind,
        name=cleaned,
        emoji=emoji,
        hidden=False,
        position=max(item.position for item in existing) + 1,
    )
    session.add(created)
    await session.flush()
    return created


async def update_category(
    session: AsyncSession,
    user: User,
    category_id: int,
    *,
    name: str | None = None,
    emoji: str | None = None,
    hidden: bool | None = None,
    budget: object = KEEP,
) -> MoneyCategory:
    """Rename (a preset too), change the emoji, hide or show, set or clear (None) the monthly
    budget of an expense category."""
    found = await category(session, user, category_id)
    if name is not None:
        found.name = await _check_name(session, user, found.kind, name, own_id=found.id)
    if emoji is not None:
        if emoji not in CATEGORY_EMOJI:
            raise InvalidInput(field="emoji", reason="not_in_set")
        found.emoji = emoji
    if hidden is not None:
        if hidden and found.preset == OTHER[found.kind]:
            raise InvalidInput(field="hidden", reason="fallback")
        found.hidden = hidden
    if budget is not KEEP:
        if found.kind != EXPENSE:
            raise InvalidInput(field="budget", reason="income")
        if budget is None:
            found.budget = None
        elif isinstance(budget, int) and not isinstance(budget, bool):
            found.budget = _check_amount(budget, "budget")
        else:
            raise InvalidInput(field="budget", reason="out_of_range")
    await session.flush()
    return found


async def set_budget(session: AsyncSession, user: User, amount: int | None) -> None:
    """The monthly budget of all expenses; None removes it."""
    user.money_budget = None if amount is None else _check_amount(amount, "budget")
    await session.flush()


async def set_currency(session: AsyncSession, user: User, code: str) -> None:
    """Only the sign changes: entries keep their numbers."""
    if code not in CURRENCIES:
        raise InvalidInput(field="currency", reason="unsupported")
    user.currency = code
    await session.flush()


def _check_day(user: User, day: date | None, now: datetime | None) -> date:
    today = local_today(user.timezone, now)
    if day is None:
        return today
    if not today - timedelta(days=OLDEST_DAY) <= day <= today:
        raise InvalidInput(field="day", reason="out_of_range")
    return day


async def _check_limits(session: AsyncSession, user: User, day: date) -> None:
    total = await session.scalar(
        select(func.count()).select_from(MoneyEntry).where(MoneyEntry.user_id == user.id)
    )
    if (total or 0) >= LIMITS.money_entries:
        raise LimitReached(entity="entry", limit=LIMITS.money_entries)
    first = day.replace(day=1)
    in_month = await session.scalar(
        select(func.count())
        .select_from(MoneyEntry)
        .where(
            MoneyEntry.user_id == user.id,
            MoneyEntry.day >= first,
            MoneyEntry.day < _next_month(first),
        )
    )
    if (in_month or 0) >= LIMITS.money_entries_month:
        raise LimitReached(entity="entry_month", limit=LIMITS.money_entries_month)


def _next_month(first: date) -> date:
    return (first + timedelta(days=32)).replace(day=1)


async def add_entry(
    session: AsyncSession,
    user: User,
    *,
    amount: int,
    category_id: int,
    note: str = "",
    day: date | None = None,
    now: datetime | None = None,
) -> MoneyEntry:
    _check_amount(amount)
    await category(session, user, category_id)
    cleaned = _clean_text(note, LIMITS.money_note_length, "note")
    when = _check_day(user, day, now)
    await _check_limits(session, user, when)
    entry = MoneyEntry(
        user_id=user.id, category_id=category_id, amount=amount, note=cleaned, day=when
    )
    session.add(entry)
    await session.flush()
    return entry


async def entry(session: AsyncSession, user: User, entry_id: int) -> MoneyEntry:
    found = await session.scalar(
        select(MoneyEntry).where(MoneyEntry.id == entry_id, MoneyEntry.user_id == user.id)
    )
    if found is None:
        raise NotFound(entity="entry")
    return found


async def update_entry(
    session: AsyncSession,
    user: User,
    entry_id: int,
    *,
    amount: int | None = None,
    category_id: int | None = None,
    note: str | None = None,
    day: date | None = None,
    now: datetime | None = None,
) -> MoneyEntry:
    """Change any field; another category may be of the other kind (an expense becomes an
    income)."""
    found = await entry(session, user, entry_id)
    if amount is not None:
        found.amount = _check_amount(amount)
    if category_id is not None:
        await category(session, user, category_id)
        found.category_id = category_id
    if note is not None:
        found.note = _clean_text(note, LIMITS.money_note_length, "note")
    if day is not None:
        new_day = _check_day(user, day, now)
        if (new_day.year, new_day.month) != (found.day.year, found.day.month):
            await _check_limits(session, user, new_day)
        found.day = new_day
    await session.flush()
    return found


async def delete_entry(session: AsyncSession, user: User, entry_id: int) -> bool:
    result = await session.execute(
        sql_delete(MoneyEntry).where(MoneyEntry.id == entry_id, MoneyEntry.user_id == user.id)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def remember(session: AsyncSession, user: User, note: str, category_id: int) -> None:
    """The next entry with this note goes to this category."""
    key = note_key(note)
    if not key:
        return
    found = await session.get(MoneyWord, (user.id, key))
    if found is None:
        session.add(MoneyWord(user_id=user.id, key=key, category_id=category_id))
    else:
        found.category_id = category_id
    await session.flush()


async def recall(session: AsyncSession, user: User, note: str) -> int | None:
    key = note_key(note)
    if not key:
        return None
    found = await session.get(MoneyWord, (user.id, key))
    return None if found is None else found.category_id


def _fits(category: MoneyCategory, income: bool | None) -> bool:
    return income is None or category.kind == (INCOME if income else EXPENSE)


async def guess_category(session: AsyncSession, user: User, quick: Quick) -> MoneyCategory:
    """Where «кофе 250» goes: the category the user last moved this note to, else the one its
    words name, else «Другое» of the phrase's kind. A hidden category is never chosen."""
    visible = {item.id: item for item in await categories(session, user, visible=True)}
    remembered = await recall(session, user, quick.note)
    mine = visible.get(remembered) if remembered is not None else None
    if mine is not None and _fits(mine, quick.income):
        return mine
    by_preset = {item.preset: item for item in visible.values() if item.preset is not None}
    key = dictionary_guess(quick.note)
    if key is not None and key in by_preset and _fits(by_preset[key], quick.income):
        return by_preset[key]
    kind = INCOME if quick.income else EXPENSE
    return by_preset[OTHER[kind]]
