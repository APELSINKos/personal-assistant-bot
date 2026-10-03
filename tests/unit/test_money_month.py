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


async def test_a_share_is_rounded_half_up(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    await spend(session, user, "cafe", 100, date(2026, 10, 1))
    await spend(session, user, "groceries", 700, date(2026, 10, 1))
    month = await money_month.month(session, user, now=NOW)
    assert [(t.category.preset, t.share) for t in month.expenses] == [
        ("groceries", 88), ("cafe", 13),
    ]  # fmt: skip


async def test_a_month_across_the_new_year(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    await money.set_budget(session, user, 3100000)
    new_year = datetime(2027, 1, 2, 9, 0, tzinfo=UTC)
    await spend(session, user, "cafe", 1000, date(2026, 12, 31), now=new_year)
    await spend(session, user, "cafe", 2000, date(2027, 1, 1), now=new_year)
    january = await money_month.month(session, user, now=new_year)
    assert (january.first, january.spent, january.count, len(january.days)) == (
        date(2027, 1, 1), 2000, 1, 31,
    )  # fmt: skip
    assert january.days[:3] == [2000, 0, None]
    assert january.per_day == (3100000 - 2000) // 30  # 2 to 31 January
    december = await money_month.month(session, user, date(2026, 12, 20), now=new_year)
    assert (december.first, december.spent, december.count, december.per_day) == (
        date(2026, 12, 1), 1000, 1, None,
    )  # fmt: skip
    assert december.days[30] == 1000
    eve = datetime(2026, 12, 31, 9, 0, tzinfo=UTC)
    assert (await money_month.month(session, user, now=eve)).per_day == 3100000 - 1000


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


async def test_the_rest_per_day_is_for_the_current_month_only(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    await money.set_budget(session, user, 3000000)
    await spend(session, user, "groceries", 100000, date(2026, 9, 10))
    for now in (datetime(2026, 10, 1, 9, 0, tzinfo=UTC), NOW):  # September on 1 and 3 October
        september = await money_month.month(session, user, date(2026, 9, 1), now=now)
        assert (september.left, september.per_day) == (2900000, None)
    november = await money_month.month(session, user, date(2026, 11, 1), now=NOW)
    assert (november.left, november.per_day, november.days) == (3000000, None, [None] * 30)
    await spend(session, user, "groceries", 3000000, date(2026, 10, 2))  # all of it
    october = await money_month.month(session, user, now=NOW)
    assert (october.left, october.per_day) == (0, None)


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


async def test_an_entry_just_after_midnight_on_the_1st_counts_in_the_new_month(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()  # Moscow
    await money.set_budget(session, user, 100000)
    await spend(session, user, "cafe", 90000, date(2026, 9, 30))
    night = datetime(2026, 9, 30, 21, 30, tzinfo=UTC)  # 00:30 on 1 October in Moscow
    cafe = await preset(session, user, "cafe")
    entry = await money.add_entry(session, user, amount=85000, category_id=cafe.id, now=night)
    assert entry.day == date(2026, 10, 1)
    october = await money_month.month(session, user, now=night)
    assert (october.first, october.spent) == (date(2026, 10, 1), 85000)
    found = await money_month.alerts_after(session, user, entry, night)
    assert [(alert.threshold, alert.spent) for alert in found] == [(80, 85000)]  # not 175 000


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


async def test_each_budget_warns_for_itself_and_only_expenses_count(
    session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    cafe, salary = await preset(session, user, "cafe"), await preset(session, user, "salary")
    await spend(session, user, "cafe", 9000, date(2026, 10, 2))
    await money.add_entry(
        session, user, amount=500000, category_id=salary.id, day=date(2026, 10, 2), now=NOW
    )
    await money.update_category(session, user, cafe.id, budget=10000)
    await money.set_budget(session, user, 10000)
    entry = await money.add_entry(session, user, amount=100, category_id=cafe.id, now=NOW)
    found = await money_month.alerts_after(session, user, entry, NOW)
    assert [(a.category.preset if a.category else None, a.threshold, a.spent) for a in found] == [
        ("cafe", 80, 9100), (None, 80, 9100),
    ]  # fmt: skip


async def test_a_changed_budget_warns_afresh(session: AsyncSession, make_user: MakeUser) -> None:
    user = await make_user()
    cafe = await preset(session, user, "cafe")
    await money.set_budget(session, user, 100000)
    await money.update_category(session, user, cafe.id, budget=10000)

    async def add(amount: int) -> list[tuple[str | None, int]]:
        entry = await money.add_entry(session, user, amount=amount, category_id=cafe.id, now=NOW)
        found = await money_month.alerts_after(session, user, entry, NOW)
        return [(a.category.preset if a.category else None, a.threshold) for a in found]

    assert await add(100000) == [("cafe", 100), (None, 100)]
    await money.set_budget(session, user, 100000)  # the same budgets: nothing new
    await money.update_category(session, user, cafe.id, budget=10000)
    assert await add(100) == []
    await money.set_budget(session, user, 200000)  # raised: their thresholds count again
    await money.update_category(session, user, cafe.id, budget=200000)
    assert await add(60000) == [("cafe", 80), (None, 80)]


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
