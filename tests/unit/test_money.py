from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.i18n import translator
from assistant.core.models import MoneyCategory, User
from assistant.core.money_style import CATEGORY_EMOJI, EXPENSE, INCOME, PRESETS
from assistant.core.services import money
from assistant.core.services.money_phrases import Quick

NOW = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)  # noon in Moscow
TODAY = date(2026, 10, 3)
MakeUser = Callable[..., Awaitable[User]]


async def preset(session: AsyncSession, user: User, key: str) -> MoneyCategory:
    return next(item for item in await money.categories(session, user) if item.preset == key)


async def test_the_presets_are_created_once_in_their_order(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    first = await money.categories(session, user)
    assert [item.preset for item in first] == [p.key for p in PRESETS]
    assert [item.id for item in await money.categories(session, user)] == [i.id for i in first]
    assert len(await money.categories(session, user, kind=EXPENSE)) == 12
    assert len(await money.categories(session, user, kind=INCOME)) == 4


async def test_a_preset_is_named_in_the_users_language_until_renamed(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    cafe = await preset(session, user, "cafe")
    assert money.name_of(cafe, translator("ru")) == "Кафе"
    assert money.name_of(cafe, translator("en")) == "Eating out"
    await money.update_category(session, user, cafe.id, name="Кофейни")
    assert money.name_of(cafe, translator("en")) == "Кофейни"


async def test_own_categories_with_a_unique_name_and_an_emoji_of_the_set(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    gym = await money.create_category(session, user, EXPENSE, "  Спорт  зал ", "💇")
    assert (gym.name, gym.kind, gym.position, gym.hidden) == ("Спорт зал", EXPENSE, 16, False)
    for name in ("кафе", "eating OUT", "спорт зал"):  # a preset in any language, or its own
        with pytest.raises(InvalidInput) as error:
            await money.create_category(session, user, EXPENSE, name, "☕")
        assert error.value.params == {"field": "name", "reason": "duplicate"}
    # The same name is fine for the other kind: «Зарплата» is an income preset.
    await money.create_category(session, user, EXPENSE, "Зарплата", "💼")
    for kind, name, emoji, field in (
        (EXPENSE, "Ж" * 31, "☕", "name"),
        (EXPENSE, "   ", "☕", "name"),
        (EXPENSE, "Цели", "🎯", "emoji"),
        ("loan", "Долг", "☕", "kind"),
    ):
        with pytest.raises(InvalidInput) as error:
            await money.create_category(session, user, kind, name, emoji)
        assert error.value.params["field"] == field


async def test_at_most_40_categories_with_the_presets(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    for number in range(LIMITS.money_categories - len(PRESETS)):
        await money.create_category(session, user, EXPENSE, f"Своя {number}", CATEGORY_EMOJI[0])
    with pytest.raises(LimitReached):
        await money.create_category(session, user, INCOME, "Ещё одна", CATEGORY_EMOJI[0])


async def test_a_category_is_hidden_shown_and_given_a_budget(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    cafe = await preset(session, user, "cafe")
    await money.update_category(session, user, cafe.id, hidden=True, emoji="🍔", budget=500000)
    assert (cafe.hidden, cafe.emoji, cafe.budget) == (True, "🍔", 500000)
    assert cafe not in await money.categories(session, user, visible=True)
    await money.update_category(session, user, cafe.id, hidden=False, budget=None)
    assert (cafe.hidden, cafe.budget) == (False, None)
    for key, changes, reason in (
        ("other", {"hidden": True}, "fallback"),
        ("other_in", {"hidden": True}, "fallback"),
        ("salary", {"budget": 100}, "income"),
        ("cafe", {"budget": 0}, "out_of_range"),
        ("cafe", {"emoji": "🎯"}, "not_in_set"),
        ("cafe", {"name": "Продукты"}, "duplicate"),
    ):
        category = await preset(session, user, key)
        with pytest.raises(InvalidInput) as error:
            await money.update_category(session, user, category.id, **changes)  # type: ignore[arg-type]
        assert error.value.params["reason"] == reason


async def test_categories_belong_to_their_user(session: AsyncSession, make_user: MakeUser) -> None:
    owner, other = await make_user(1), await make_user(2)
    cafe = await preset(session, owner, "cafe")
    with pytest.raises(NotFound):
        await money.update_category(session, other, cafe.id, hidden=True)
    with pytest.raises(NotFound):
        await money.add_entry(session, other, amount=100, category_id=cafe.id, now=NOW)


async def test_an_entry_is_dated_today_by_default_and_up_to_366_days_back(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    cafe = await preset(session, user, "cafe")
    entry = await money.add_entry(
        session, user, amount=25000, category_id=cafe.id, note=" кофе\tс\x07собой ", now=NOW
    )
    assert (entry.amount, entry.note, entry.day) == (25000, "кофе с собой", TODAY)
    oldest = TODAY - timedelta(days=366)
    assert (
        await money.add_entry(session, user, amount=1, category_id=cafe.id, day=oldest, now=NOW)
    ).day == oldest
    for changes, field in (
        ({"amount": 0}, "amount"),
        ({"amount": 100_000_000_001}, "amount"),
        ({"amount": 100, "note": "ж" * 101}, "note"),
        ({"amount": 100, "day": TODAY + timedelta(days=1)}, "day"),
        ({"amount": 100, "day": oldest - timedelta(days=1)}, "day"),
    ):
        with pytest.raises(InvalidInput) as error:
            await money.add_entry(session, user, category_id=cafe.id, now=NOW, **changes)  # type: ignore[arg-type]
        assert error.value.params["field"] == field


async def test_an_entry_changes_and_goes(session: AsyncSession, make_user: MakeUser) -> None:
    user, stranger = await make_user(1), await make_user(2)
    cafe, salary = await preset(session, user, "cafe"), await preset(session, user, "salary")
    entry = await money.add_entry(session, user, amount=25000, category_id=cafe.id, now=NOW)
    changed = await money.update_entry(
        session, user, entry.id, amount=500000, category_id=salary.id, note="аванс",
        day=date(2026, 9, 30), now=NOW,
    )  # fmt: skip
    assert (changed.amount, changed.category_id, changed.note, changed.day) == (
        500000, salary.id, "аванс", date(2026, 9, 30),
    )  # fmt: skip
    with pytest.raises(NotFound):
        await money.update_entry(session, stranger, entry.id, amount=1, now=NOW)
    assert not await money.delete_entry(session, stranger, entry.id)
    assert await money.delete_entry(session, user, entry.id)
    assert not await money.delete_entry(session, user, entry.id)
    with pytest.raises(NotFound):
        await money.entry(session, user, entry.id)


async def test_entries_are_limited_in_all_and_per_month(
    session: AsyncSession, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user()
    cafe = await preset(session, user, "cafe")
    monkeypatch.setattr(money, "LIMITS", replace(LIMITS, money_entries_month=1, money_entries=2))
    first = await money.add_entry(session, user, amount=1, category_id=cafe.id, now=NOW)
    with pytest.raises(LimitReached) as error:
        await money.add_entry(session, user, amount=1, category_id=cafe.id, now=NOW)
    assert error.value.params["entity"] == "entry_month"
    september = date(2026, 9, 15)
    second = await money.add_entry(
        session, user, amount=1, category_id=cafe.id, day=september, now=NOW
    )
    with pytest.raises(LimitReached) as error:
        await money.add_entry(session, user, amount=1, category_id=cafe.id, now=NOW)
    assert error.value.params["entity"] == "entry"
    with pytest.raises(LimitReached) as error:  # moving the October entry into a full September
        await money.update_entry(session, user, first.id, day=september, now=NOW)
    assert (error.value.params["entity"], first.day) == ("entry_month", TODAY)
    # A move adds no entry: at the total cap an entry still goes to a month with room, and a
    # new day in its own month is no move at all.
    for day in (date(2026, 8, 20), date(2026, 8, 1)):
        assert (await money.update_entry(session, user, second.id, day=day, now=NOW)).day == day


async def test_a_refused_change_changes_nothing(session: AsyncSession, make_user: MakeUser) -> None:
    user, stranger = await make_user(1), await make_user(2)
    cafe, theirs = await preset(session, user, "cafe"), await preset(session, stranger, "cafe")
    oldest = TODAY - timedelta(days=366)
    entry = await money.add_entry(
        session, user, amount=100, category_id=cafe.id, note="кофе", day=oldest, now=NOW
    )
    for changes, field in (
        ({"amount": 999, "note": "ж" * 101}, "note"),
        ({"note": "чай", "amount": 0}, "amount"),
        ({"amount": 999, "day": TODAY + timedelta(days=1)}, "day"),
    ):
        with pytest.raises(InvalidInput) as error:
            await money.update_entry(session, user, entry.id, now=NOW, **changes)  # type: ignore[arg-type]
        assert error.value.params["field"] == field
    with pytest.raises(NotFound):
        await money.update_entry(session, user, entry.id, amount=999, category_id=theirs.id)
    assert (entry.amount, entry.note, entry.day, entry.category_id) == (
        100, "кофе", oldest, cafe.id,
    )  # fmt: skip
    # A month on, the entry's day is out of the window, yet the entry is saved with it.
    later = NOW + timedelta(days=30)
    saved = await money.update_entry(session, user, entry.id, amount=200, day=oldest, now=later)
    assert (saved.amount, saved.day) == (200, oldest)
    with pytest.raises(InvalidInput):  # a new day keeps to the window
        await money.update_entry(
            session, user, entry.id, day=TODAY - timedelta(days=365), now=later
        )


async def test_a_moved_note_is_remembered(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    cafe, groceries = await preset(session, user, "cafe"), await preset(session, user, "groceries")
    await money.remember(session, user, "Кофе", cafe.id)
    assert await money.recall(session, user, "кофе!") == cafe.id
    await money.remember(session, user, "кофе", groceries.id)
    assert await money.recall(session, user, "КОФЕ") == groceries.id
    await money.remember(session, user, "  !! ", cafe.id)  # nothing to remember
    assert await money.recall(session, user, "") is None
    stranger = await make_user(2)
    for owner, category_id in ((stranger, cafe.id), (user, 10**6)):
        with pytest.raises(NotFound):  # someone else's category, or none at all
            await money.remember(session, owner, "кофе", category_id)


async def test_the_category_of_a_quick_phrase(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()

    async def guessed(note: str, income: bool | None = None) -> str | None:
        return (await money.guess_category(session, user, Quick(100, note, income))).preset

    assert await guessed("кофе") == "cafe"
    assert await guessed("стипендия") == "stipend"
    assert await guessed("") == "other"
    assert await guessed("xyz") == "other"
    assert await guessed("кофе", income=True) == "other_in"  # «+250 кофе»: an income
    assert await guessed("стипендия", income=False) == "other"
    groceries = await preset(session, user, "groceries")
    await money.remember(session, user, "кофе", groceries.id)
    assert await guessed("кофе") == "groceries"  # the user's choice beats the words
    await money.update_category(session, user, groceries.id, hidden=True)
    assert await guessed("кофе") == "cafe"  # never a hidden category
    await money.update_category(
        session, user, (await preset(session, user, "cafe")).id, hidden=True
    )
    assert await guessed("кофе") == "other"


async def test_the_budget_and_the_currency(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    assert (user.currency, user.money_budget) == ("RUB", None)
    await money.set_budget(session, user, 3000000)
    assert user.money_budget == 3000000
    await money.set_budget(session, user, None)
    assert user.money_budget is None
    with pytest.raises(InvalidInput):
        await money.set_budget(session, user, 0)
    await money.set_currency(session, user, "USD")
    assert user.currency == "USD"
    with pytest.raises(InvalidInput) as error:
        await money.set_currency(session, user, "XXX")
    assert error.value.params == {"field": "currency", "reason": "unsupported"}
