"""Extra cities of the weather: up to LIMITS.cities besides the home city.

The home city stays in `users` and alone sets the time of everything else (reminders, the digest,
habits, money, the timetable). An extra city changes nothing but the weather shown. Two cities
are one when they have the same GeoNames id or, when one of them has none (the home city never
has one), when they are one place to 0.01°."""

from __future__ import annotations

import unicodedata

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.clients.openmeteo import City
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import User, WeatherCity
from assistant.core.timeutil import is_valid_timezone

NAME_LENGTH = 100  # a name, a region or a country as kept: the columns' size (the home city's too)
NEAR = 0.01  # degrees on each axis within which two points are one place, about a kilometre
_SLACK = 1e-9  # in floats 55.76 - 55.75 is 0.010000000000005116


def same_place(lat1: float, lon1: float, lat2: float, lon2: float) -> bool:
    """Whether two points are one place for the weather: within NEAR on both axes. Longitudes
    are compared the short way round, across the 180th meridian too."""
    east = abs(lon1 - lon2) % 360
    return abs(lat1 - lat2) <= NEAR + _SLACK and min(east, 360 - east) <= NEAR + _SLACK


def clean_name(text: str) -> str:
    """A place's name as kept: control characters (a tab, a line break) become spaces, runs of
    spaces one space, and the ends go."""
    spaced = "".join(" " if unicodedata.category(char) == "Cc" else char for char in text)
    return " ".join(spaced.split())


async def list_for(session: AsyncSession, user_id: int) -> list[WeatherCity]:
    """The user's extra cities in the order they were added."""
    rows = await session.scalars(
        select(WeatherCity).where(WeatherCity.user_id == user_id).order_by(WeatherCity.id)
    )
    return list(rows)


async def get(session: AsyncSession, user_id: int, city_id: int) -> WeatherCity:
    city = await session.scalar(
        select(WeatherCity).where(WeatherCity.id == city_id, WeatherCity.user_id == user_id)
    )
    if city is None:
        raise NotFound(entity="city")
    return city


async def add(session: AsyncSession, user: User, city: City) -> WeatherCity:
    """Keep a place the search found as an extra city of the user; the home city is untouched.

    LimitReached when LIMITS.cities are on the list already. InvalidInput(field="city") with
    reason "duplicate" for the home city or a city on the list, "invalid" for a place that
    cannot be kept: no name, a zone the server does not know, coordinates out of range."""
    columns = _columns(city)
    kept = await list_for(session, user.id)
    # Checked before writing and without a lock, as for notes: the bot and the app adding at
    # once may end one city over the limit, which nothing minds.
    if len(kept) >= LIMITS.cities:
        raise LimitReached(entity="city", limit=LIMITS.cities)
    if same_place(city.lat, city.lon, user.lat, user.lon) or any(
        (city.geo_id is None or other.geo_id is None)
        and same_place(city.lat, city.lon, other.lat, other.lon)
        for other in kept
    ):
        raise InvalidInput(field="city", reason="duplicate")
    # A GeoNames place already on the list, even one added a moment ago from the other side,
    # meets the unique key: then nothing is written and nothing comes back.
    added: WeatherCity | None = await session.scalar(
        sqlite_insert(WeatherCity)
        .values(user_id=user.id, **columns)
        .on_conflict_do_nothing(index_elements=["user_id", "geo_id"])
        .returning(WeatherCity)
    )
    if added is None:
        raise InvalidInput(field="city", reason="duplicate")
    return added


def _columns(city: City) -> dict[str, object]:
    """What is kept of a place, or InvalidInput. The search offers only places that can be
    kept, but the app sends its own copy of one."""
    name, admin, country = (
        clean_name(text or "") for text in (city.name, city.admin, city.country)
    )
    fits = (
        name
        and max(len(name), len(admin), len(country)) <= NAME_LENGTH
        and is_valid_timezone(city.timezone)
        and -90 <= city.lat <= 90
        and -180 <= city.lon <= 180
        and (city.geo_id is None or 0 < city.geo_id < 2**63)  # SQLite's INTEGER
    )
    if not fits:
        raise InvalidInput(field="city", reason="invalid")
    return {
        "name": name,
        "admin": admin or None,
        "country": country or None,
        "lat": city.lat,
        "lon": city.lon,
        "timezone": city.timezone,
        "geo_id": city.geo_id,
    }


async def delete(session: AsyncSession, user_id: int, city_id: int) -> None:
    result = await session.execute(
        sql_delete(WeatherCity).where(WeatherCity.id == city_id, WeatherCity.user_id == user_id)
    )
    if not result.rowcount:  # type: ignore[attr-defined]
        raise NotFound(entity="city")


async def remove_place(
    session: AsyncSession, user_id: int, lat: float, lon: float, geo_id: int | None = None
) -> None:
    """Take a place off the user's list, found by its GeoNames id or by its coordinates: it is
    becoming the home city, and the list never holds the home city."""
    for city in await list_for(session, user_id):
        if (geo_id is not None and city.geo_id == geo_id) or same_place(
            lat, lon, city.lat, city.lon
        ):
            await session.delete(city)
    await session.flush()
