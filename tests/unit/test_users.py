from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from assistant.core.clients.openmeteo import City
from assistant.core.errors import InvalidInput
from assistant.core.models import Reminder, ReminderStatus, Repeat, User
from assistant.core.services import cities, reminders, users
from assistant.core.services.recurrence import Rule

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
TULA = City(
    name="Тула",
    admin="Тульская область",
    country="Россия",
    lat=54.19,
    lon=37.62,
    timezone="Europe/Moscow",
    geo_id=480562,
)
SOCHI = replace(TULA, name="Сочи", admin="Краснодарский край", lat=43.6, lon=39.73, geo_id=491422)


async def test_ensure_creates_with_defaults(session) -> None:
    user = await users.ensure(session, 7, "Alex", "ru")
    assert (user.city, user.timezone, user.morning_time, user.morning_enabled) == (
        "Москва",
        "Europe/Moscow",
        "08:00",
        True,
    )
    assert user.language is None and user.tg_language == "ru" and not user.bot_blocked


async def test_ensure_from_two_sessions_at_once_creates_one_user(sessionmaker) -> None:
    both_connected = asyncio.Barrier(2)

    async def first_contact(first_name: str) -> int:
        async with sessionmaker() as db:
            # Connect first, so that both lookups really run side by side.
            await db.connection()
            await both_connected.wait()
            user = await users.ensure(db, 9, first_name, "ru")
            await db.commit()
            return user.id

    assert await asyncio.gather(first_contact("Alex"), first_contact("Sasha")) == [9, 9]
    async with sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 1


async def test_ensure_unblocks_and_expires_old_reminders(session, make_user) -> None:
    await make_user(id=5, bot_blocked=True)
    old = NOW - timedelta(days=2)
    fresh = NOW - timedelta(hours=1)
    session.add_all(
        [
            Reminder(user_id=5, text="old", due_at=old, next_attempt_at=old),
            Reminder(user_id=5, text="fresh", due_at=fresh, next_attempt_at=fresh),
        ]
    )
    await session.commit()
    user = await users.ensure(session, 5, "Test", "ru", now=NOW)
    await session.commit()
    assert not user.bot_blocked
    statuses = {
        r.text: (r.status, r.last_error) for r in (await session.scalars(select(Reminder))).all()
    }
    assert statuses == {
        "old": (ReminderStatus.FAILED, "expired"),
        "fresh": (ReminderStatus.PENDING, None),
    }


async def test_an_unblock_expires_and_moves_only_the_users_own_reminders(
    session, make_user
) -> None:
    await make_user(id=5, bot_blocked=True)
    neighbour = await make_user(id=6, bot_blocked=True)  # away as well, and staying away
    long_ago = NOW - timedelta(days=3)
    await reminders.create(session, neighbour, "старое", datetime(2026, 9, 25, 18), long_ago)
    daily = Rule(repeat=Repeat.DAILY, time_local="10:00", anchor_date=date(2026, 9, 25))
    await reminders.create_repeating(session, neighbour, "таблетки", daily, long_ago)
    await session.commit()

    async def theirs() -> dict[str, tuple[ReminderStatus, datetime]]:
        rows = (await session.scalars(select(Reminder))).all()
        return {row.text: (row.status, row.due_at) for row in rows}

    kept = await theirs()
    await users.ensure(session, 5, "Test", "ru", now=NOW)  # user 5 writes to the bot again
    await session.commit()
    session.expire_all()
    assert await theirs() == kept
    assert {status for status, _ in kept.values()} == {ReminderStatus.PENDING}


async def test_set_morning_validates_time(session, make_user) -> None:
    user = await make_user()
    await users.set_morning(session, user, time="7:5", enabled=False)
    assert (user.morning_time, user.morning_enabled) == ("07:05", False)
    with pytest.raises(InvalidInput):
        await users.set_morning(session, user, time="25:00")


async def test_set_language_validates(session, make_user) -> None:
    user = await make_user()
    await users.set_language(session, user, "en")
    assert user.language == "en"
    await users.set_language(session, user, None)
    assert user.language is None
    with pytest.raises(InvalidInput):
        await users.set_language(session, user, "de")


async def test_set_city_rejects_unknown_zone(session, make_user) -> None:
    user = await make_user()
    with pytest.raises(InvalidInput):
        await users.set_city(session, user, "Марс", 0, 0, "Mars/Base")


async def test_set_city_keeps_the_name_without_control_characters(session, make_user) -> None:
    user = await make_user()
    await users.set_city(session, user, " Санкт\tПетербург\x00\n", 59.94, 30.31, "Europe/Moscow")
    assert user.city == "Санкт Петербург"


async def test_set_city_takes_a_hundred_characters_counted_after_cleaning(
    session, make_user
) -> None:
    # The column's size, as for the extra cities, not the bot's limit on a search query.
    user = await make_user()
    await users.set_city(session, user, " " + "я" * 100 + "\n", 55.75, 37.62, "Europe/Moscow")
    assert user.city == "я" * 100
    with pytest.raises(InvalidInput) as error:
        await users.set_city(session, user, "я" * 101, 55.75, 37.62, "Europe/Moscow")
    assert error.value.params == {"field": "city", "reason": "invalid"}
    assert user.city == "я" * 100


async def test_a_new_home_leaves_the_extra_cities_by_its_geonames_id(session, make_user) -> None:
    user, other = await make_user(1), await make_user(2)
    for owner in (user, other):
        await cities.add(session, owner, TULA)
    await cities.add(session, user, SOCHI)
    # Тула found again, its coordinates given otherwise: its GeoNames id tells it.
    await users.set_city(session, user, "Тула", 54.2044, 37.6111, "Europe/Moscow", geo_id=480562)
    assert (user.city, user.lat, user.lon) == ("Тула", 54.2044, 37.6111)
    assert [city.name for city in await cities.list_for(session, user.id)] == ["Сочи"]
    assert [city.name for city in await cities.list_for(session, other.id)] == ["Тула"]


async def test_a_new_home_without_an_id_leaves_the_list_by_its_place(session, make_user) -> None:
    user = await make_user()
    await cities.add(session, user, TULA)
    await cities.add(session, user, SOCHI)
    await users.set_city(session, user, "Тула", 54.195, 37.615, "Europe/Moscow")
    assert [city.name for city in await cities.list_for(session, user.id)] == ["Сочи"]


@pytest.mark.parametrize("kept_id", [None, 7_000_001])
async def test_a_new_home_with_an_id_leaves_the_list_by_its_place_too(
    session, make_user, kept_id
) -> None:
    # Тула kept without a GeoNames id, or under a neighbouring one (a city and its region may
    # have two ids a kilometre apart): its place tells it, as the list never holds the home city.
    user = await make_user()
    await cities.add(session, user, replace(TULA, geo_id=kept_id))
    await cities.add(session, user, SOCHI)
    await users.set_city(session, user, "Тула", 54.195, 37.615, "Europe/Moscow", geo_id=480562)
    assert [city.name for city in await cities.list_for(session, user.id)] == ["Сочи"]


async def test_a_new_home_leaves_the_list_in_the_same_transaction(session, make_user) -> None:
    user = await make_user()
    user_id = user.id
    await cities.add(session, user, TULA)
    await session.commit()
    await users.set_city(session, user, "Тула", 54.19, 37.62, "Europe/Moscow", geo_id=480562)
    await session.rollback()
    assert (await session.get_one(User, user_id)).city == "Москва"
    assert [city.name for city in await cities.list_for(session, user_id)] == ["Тула"]


async def test_a_refused_home_keeps_the_extra_cities(session, make_user) -> None:
    user = await make_user()
    await cities.add(session, user, TULA)
    with pytest.raises(InvalidInput):
        await users.set_city(session, user, "Тула", 54.19, 37.62, "Mars/Base", geo_id=480562)
    assert [city.name for city in await cities.list_for(session, user.id)] == ["Тула"]


async def test_ensure_keeps_the_language_when_telegram_sends_none(session, make_user) -> None:
    await make_user(id=9, tg_language="uk")
    user = await users.ensure(session, 9, "Test", None)
    assert user.tg_language == "uk"
    user = await users.ensure(session, 9, "Test", "de")
    assert user.tg_language == "de"
