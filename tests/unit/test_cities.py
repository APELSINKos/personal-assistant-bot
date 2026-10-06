from __future__ import annotations

import asyncio
import math
from dataclasses import asdict, replace
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from assistant.core.clients.openmeteo import City
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import Reminder, Repeat, User, WeatherCity
from assistant.core.services import cities, reminders
from assistant.core.services.recurrence import Rule

NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
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
KAZAN = replace(TULA, name="Казань", admin="Татарстан", lat=55.79, lon=49.12, geo_id=551487)
OMSK = replace(
    TULA,
    name="Омск",
    admin="Омская область",
    lat=54.99,
    lon=73.37,
    timezone="Asia/Omsk",
    geo_id=1496153,
)
VLADIVOSTOK = replace(
    TULA,
    name="Владивосток",
    admin="Приморский край",
    lat=43.11,
    lon=131.87,
    timezone="Asia/Vladivostok",
    geo_id=2013348,
)
DUPLICATE = {"field": "city", "reason": "duplicate"}
INVALID = {"field": "city", "reason": "invalid"}


async def names(session, user_id: int) -> list[str]:
    return [city.name for city in await cities.list_for(session, user_id)]


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ((55.75, 37.62), (55.75, 37.62), True),
        ((55.75, 37.62), (55.76, 37.63), True),  # 0.01° on both axes: still one place
        ((55.75, 37.62), (55.74, 37.61), True),
        ((55.75, 37.62), (55.761, 37.62), False),
        ((55.75, 37.62), (55.75, 37.631), False),
        ((-55.75, 37.62), (55.75, 37.62), False),
        ((-16.5, 179.996), (-16.5, -179.996), True),  # across the 180th meridian
        ((-16.5, 179.99), (-16.5, -179.99), False),
    ],
)
def test_one_place_is_within_a_hundredth_of_a_degree_on_both_axes(first, second, same) -> None:
    assert cities.same_place(*first, *second) is same
    assert cities.same_place(*second, *first) is same


async def test_added_cities_are_listed_in_the_order_they_came(session, make_user) -> None:
    user = await make_user()
    added = await cities.add(session, user, TULA)
    await cities.add(session, user, SOCHI)
    await session.commit()
    assert await names(session, user.id) == ["Тула", "Сочи"]
    assert added.user_id == user.id
    assert (added.admin, added.country, added.lat, added.lon, added.timezone) == (
        "Тульская область",
        "Россия",
        54.19,
        37.62,
        "Europe/Moscow",
    )
    assert added.geo_id == 480562 and added.created_at.tzinfo is UTC


async def test_an_extra_city_moves_neither_the_home_city_nor_the_reminders(
    session, make_user
) -> None:
    user = await make_user()
    daily = Rule(repeat=Repeat.DAILY, time_local="21:00", anchor_date=date(2026, 10, 5))
    await reminders.create_repeating(session, user, "таблетки", daily, NOW)
    await reminders.create(session, user, "врач", datetime(2026, 10, 6, 10), NOW)
    await session.commit()
    moments = select(Reminder.due_at, Reminder.occurrence_at).order_by(Reminder.id)
    before = (await session.execute(moments)).all()
    user_id = user.id
    added = await cities.add(session, user, VLADIVOSTOK)  # seven hours ahead of the home city
    await cities.delete(session, user_id, added.id)
    await session.commit()
    session.expire_all()  # read again what is stored
    home = await session.get_one(User, user_id)
    assert (home.city, home.lat, home.lon, home.timezone) == (
        "Москва",
        55.75,
        37.62,
        "Europe/Moscow",
    )
    assert (await session.execute(moments)).all() == before


async def test_names_are_kept_without_control_characters(session, make_user) -> None:
    user = await make_user()
    added = await cities.add(
        session, user, replace(TULA, name=" Тула\tгород\n", admin="", country="\x00 \x85")
    )
    assert (added.name, added.admin, added.country) == ("Тула город", None, None)


async def test_names_of_a_hundred_characters_fit(session, make_user) -> None:
    user = await make_user()
    added = await cities.add(
        session, user, replace(TULA, name="я" * 100, admin="я" * 100, country="я" * 100)
    )
    assert len(added.name) == len(added.admin or "") == len(added.country or "") == 100


@pytest.mark.parametrize(
    "change",
    [
        {"timezone": "Mars/Base"},
        {"timezone": "Europe"},  # a folder of the zone database, not a zone
        {"lat": 90.5},
        {"lon": -180.5},
        {"lat": math.nan},
        {"lon": math.inf},
        {"name": ""},
        {"name": "\t\n"},
        {"name": "я" * 101},
        {"admin": "я" * 101},
        {"country": "я" * 101},
        {"geo_id": 0},
        {"geo_id": 2**63},
    ],
)
async def test_a_place_that_cannot_be_kept_is_refused(session, make_user, change) -> None:
    user = await make_user()
    with pytest.raises(InvalidInput) as error:
        await cities.add(session, user, replace(TULA, **change))
    assert error.value.params == INVALID
    assert await cities.list_for(session, user.id) == []


async def test_up_to_four_extra_cities(session, make_user) -> None:
    user = await make_user()
    for city in (TULA, SOCHI, KAZAN, OMSK):
        await cities.add(session, user, city)
    with pytest.raises(LimitReached) as error:
        await cities.add(session, user, VLADIVOSTOK)
    assert error.value.params == {"entity": "city", "limit": 4}
    # A full list says so before anything else: no other city would fit either.
    with pytest.raises(LimitReached):
        await cities.add(session, user, TULA)
    assert await names(session, user.id) == ["Тула", "Сочи", "Казань", "Омск"]


async def test_a_list_one_over_the_limit_still_works(session, make_user) -> None:
    # The limit is checked without a lock: the bot and the app adding at once may end with one
    # city too many.
    user = await make_user()
    five = (TULA, SOCHI, KAZAN, OMSK, VLADIVOSTOK)
    session.add_all([WeatherCity(user_id=user.id, **asdict(city)) for city in five])
    await session.commit()
    kept = await cities.list_for(session, user.id)
    assert len(kept) == 5
    with pytest.raises(LimitReached):
        await cities.add(session, user, replace(TULA, name="Ялта", lat=44.5, lon=34.17))
    await cities.delete(session, user.id, kept[0].id)
    assert len(await cities.list_for(session, user.id)) == 4


async def test_the_home_city_is_not_added(session, make_user) -> None:
    # The home city has no GeoNames id: its place alone tells it.
    user = await make_user()  # Москва, 55.75 37.62
    moscow = replace(TULA, name="Москва", admin="Москва", lat=55.75222, lon=37.61556, geo_id=524901)
    with pytest.raises(InvalidInput) as error:
        await cities.add(session, user, moscow)
    assert error.value.params == DUPLICATE
    assert await cities.list_for(session, user.id) == []


async def test_a_geonames_place_is_on_the_list_once(session, make_user) -> None:
    user = await make_user()
    await cities.add(session, user, TULA)
    # The same place found in English, its coordinates given otherwise: the id tells it.
    english = replace(
        TULA, name="Tula", admin="Tula Oblast", country="Russia", lat=54.2044, lon=37.6111
    )
    with pytest.raises(InvalidInput) as error:
        await cities.add(session, user, english)
    assert error.value.params == DUPLICATE
    assert await names(session, user.id) == ["Тула"]


@pytest.mark.parametrize(("kept_id", "new_id"), [(None, None), (None, 480562), (480562, None)])
async def test_without_an_id_a_city_is_told_by_its_place(
    session, make_user, kept_id, new_id
) -> None:
    user = await make_user()
    await cities.add(session, user, replace(TULA, geo_id=kept_id))
    nearby = replace(TULA, name="Tula", lat=54.195, lon=37.625, geo_id=new_id)
    with pytest.raises(InvalidInput) as error:
        await cities.add(session, user, nearby)
    assert error.value.params == DUPLICATE
    assert await names(session, user.id) == ["Тула"]


async def test_two_geonames_places_a_street_apart_are_two_cities(session, make_user) -> None:
    user = await make_user()
    await cities.add(session, user, TULA)
    await cities.add(session, user, replace(TULA, name="Тула-1", lat=54.195, geo_id=7_000_001))
    assert await names(session, user.id) == ["Тула", "Тула-1"]


async def test_a_city_far_from_the_others_is_added_without_an_id(session, make_user) -> None:
    user = await make_user()
    await cities.add(session, user, replace(TULA, geo_id=None))
    await cities.add(session, user, replace(SOCHI, geo_id=None))
    assert await names(session, user.id) == ["Тула", "Сочи"]


async def test_each_user_has_their_own_cities(session, make_user) -> None:
    first, second = await make_user(1), await make_user(2)
    theirs = await cities.add(session, second, TULA)
    mine = await cities.add(session, first, TULA)  # the same GeoNames place, another user
    assert [city.id for city in await cities.list_for(session, first.id)] == [mine.id]
    with pytest.raises(NotFound) as error:
        await cities.get(session, first.id, theirs.id)
    assert error.value.params == {"entity": "city"}
    with pytest.raises(NotFound):
        await cities.delete(session, first.id, theirs.id)
    assert [city.id for city in await cities.list_for(session, second.id)] == [theirs.id]


async def test_get_and_delete(session, make_user) -> None:
    user = await make_user()
    gone = (await cities.add(session, user, TULA)).id
    await session.commit()
    assert (await cities.get(session, user.id, gone)).name == "Тула"
    await cities.delete(session, user.id, gone)
    await session.commit()
    assert await cities.list_for(session, user.id) == []
    with pytest.raises(NotFound):
        await cities.get(session, user.id, gone)
    with pytest.raises(NotFound) as error:
        await cities.delete(session, user.id, gone)
    assert error.value.params == {"entity": "city"}
    # Back on the list it is a new city: the old buttons with its id stay dead.
    assert (await cities.add(session, user, TULA)).id > gone


async def test_two_adds_of_one_place_at_once_keep_one_city(sessionmaker, make_user) -> None:
    # The bot and the app may add the same city at the same moment: the unique key keeps one.
    await make_user()
    both_connected = asyncio.Barrier(2)

    async def add() -> str:
        async with sessionmaker() as db:
            # Connect first, so that both lookups really run side by side.
            await db.connection()
            await both_connected.wait()
            try:
                await cities.add(db, await db.get_one(User, 1), TULA)
            except InvalidInput as error:
                return str(error.params["reason"])
            await db.commit()
            return "added"

    assert sorted(await asyncio.gather(add(), add())) == ["added", "duplicate"]
    async with sessionmaker() as db:
        assert await names(db, 1) == ["Тула"]
