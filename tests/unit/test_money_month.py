from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.models import MoneyCategory, User
from assistant.core.services import money, money_month

NOW = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)  # 3 October, noon in Moscow
MakeUser = Callable[..., Awaitable[User]]


async def preset(session: AsyncSession, user: User, key: str) -> MoneyCategory:
    return next(item for item in await money.categories(session, user) if item.preset == key)


async def spend(
    session: AsyncSession, user: User, key: str, amount: int, day: date, now: datetime = NOW
) -> None:
    category = await preset(session, user, key)
    await money.add_entry(session, user, amount=amount, category_id=category.id, day=day, now=now)


async def test_an_empty_month(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    month = await money_month.month(session, user, now=NOW)
    assert (month.first, month.today, month.spent, month.income, month.count) == (
        date(2026, 10, 1), date(2026, 10, 3), 0, 0, 0,
    )  # fmt: skip
    assert (month.budget, month.left, month.per_day, month.balance) == (None, None, None, 0)
    assert month.days == [0, 0, 0] + [None] * 28  # the days still ahead are not zero
    assert await money_month.first_month(session, user) is None


async def test_a_month_by_category_and_by_day(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    await spend(session, user, "groceries", 300000, date(2026, 10, 1))
    await spend(session, user, "cafe", 25000, date(2026, 10, 1))
    await spend(session, user, "cafe", 75000, date(2026, 10, 3))
    await spend(session, user, "stipend", 500000, date(2026, 10, 2))
    await spend(session, user, "cafe", 99900, date(2026, 9, 30))  # September
    month = await money_month.month(session, user, now=NOW)
    assert (month.spent, month.income, month.balance, month.count) == (400000, 500000, 100000, 4)
    assert [(t.category.preset, t.amount, t.share) for t in month.expenses] == [
        ("groceries", 300000, 75), ("cafe", 100000, 25),
    ]  # fmt: skip
    assert [(t.category.preset, t.amount, t.share) for t in month.incomes] == [
        ("stipend", 500000, 0)
    ]
    assert month.days[:4] == [325000, 0, 75000, None]
    assert await money_month.first_month(session, user) == date(2026, 9, 1)
    september = await money_month.month(session, user, date(2026, 9, 14), now=NOW)
    assert (september.first, september.spent, september.per_day) == (date(2026, 9, 1), 99900, None)
    assert None not in september.days and len(september.days) == 30
    newest = await money_month.entries(session, user, date(2026, 10, 1))
    assert [(entry.day.day, entry.amount) for entry, _ in newest] == [
        (3, 75000), (2, 500000), (1, 25000), (1, 300000),
    ]  # fmt: skip
    cafe = await preset(session, user, "cafe")
    only = await money_month.entries(session, user, date(2026, 10, 1), category_id=cafe.id)
    assert [entry.amount for entry, _ in only] == [75000, 25000]


async def test_the_month_is_the_users_local_one(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user(tz="Asia/Vladivostok")
    evening = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)  # already 1 October in Vladivostok
    month = await money_month.month(session, user, now=evening)
    assert (month.first, month.today) == (date(2026, 10, 1), date(2026, 10, 1))


async def test_the_budgets_rest_for_each_day_left(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    await money.set_budget(session, user, 3000000)
    await spend(session, user, "groceries", 2435000, date(2026, 10, 2))
    month = await money_month.month(session, user, now=NOW)
    assert (month.budget, month.left) == (3000000, 565000)
    assert month.per_day == 565000 // 29  # 3 to 31 October
    last_day = datetime(2026, 10, 31, 9, 0, tzinfo=UTC)
    assert (await money_month.month(session, user, now=last_day)).per_day == 565000
    await spend(session, user, "cafe", 600000, date(2026, 10, 3))
    over = await money_month.month(session, user, now=NOW)
    assert (over.left, over.per_day) == (-35000, None)


async def test_a_category_budgets_rest(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    cafe = await preset(session, user, "cafe")
    await money.update_category(session, user, cafe.id, budget=500000)
    await spend(session, user, "cafe", 530000, date(2026, 10, 2))
    await spend(session, user, "groceries", 1000, date(2026, 10, 2))
    month = await money_month.month(session, user, now=NOW)
    assert [(t.category.preset, t.left) for t in month.expenses] == [
        ("cafe", -30000), ("groceries", None),
    ]  # fmt: skip


async def test_a_warning_comes_once_per_threshold_and_month(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    cafe = await preset(session, user, "cafe")
    await money.set_budget(session, user, 100000)

    async def add(amount: int, now: datetime = NOW) -> list[tuple[int, int]]:
        day = now.date()
        entry = await money.add_entry(
            session, user, amount=amount, category_id=cafe.id, day=day, now=now
        )
        found = await money_month.alerts_after(session, user, entry, now)
        return [(alert.threshold, alert.spent) for alert in found]

    assert await add(79000) == []
    assert await add(2000) == [(80, 81000)]
    assert await add(500) == []
    assert await add(30000) == [(100, 111500)]
    assert await add(1000) == []
    november = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    assert await add(100000, november) == [(100, 100000)]  # both at once: the higher one
    assert await add(100, november) == []  # 80 was kept too


async def test_a_category_budget_warns_on_its_own(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    cafe = await preset(session, user, "cafe")
    await money.update_category(session, user, cafe.id, budget=10000)
    entry = await money.add_entry(session, user, amount=9000, category_id=cafe.id, now=NOW)
    found = await money_month.alerts_after(session, user, entry, NOW)
    assert [(a.category.preset if a.category else None, a.threshold) for a in found] == [
        ("cafe", 80)
    ]


async def test_no_warning_for_an_income_a_past_month_or_without_a_budget(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    cafe, salary = await preset(session, user, "cafe"), await preset(session, user, "salary")
    entry = await money.add_entry(session, user, amount=999900, category_id=cafe.id, now=NOW)
    assert await money_month.alerts_after(session, user, entry, NOW) == []  # no budget
    await money.set_budget(session, user, 1000)
    income = await money.add_entry(session, user, amount=999900, category_id=salary.id, now=NOW)
    assert await money_month.alerts_after(session, user, income, NOW) == []
    past = await money.add_entry(
        session, user, amount=999900, category_id=cafe.id, day=date(2026, 9, 30), now=NOW
    )
    assert await money_month.alerts_after(session, user, past, NOW) == []
