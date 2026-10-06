from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from assistant.core.clients.openmeteo import OpenMeteoClient, check_forecast
from assistant.core.errors import UpstreamUnavailable
from assistant.core.i18n import translator
from assistant.core.services import weather
from assistant.core.services.weather import (
    ClassesWeather,
    Day,
    Forecast,
    Hour,
    Tip,
    WeatherNow,
    chance_after,
    classes_weather,
    current,
    days_from,
    describe,
    hour_of,
    local_now,
    next_hours,
    parse,
    polar,
    tomorrow,
)
from tests.stubs import FORECAST_NOW, forecast_payload

MOSCOW = ZoneInfo("Europe/Moscow")
BERLIN = ZoneInfo("Europe/Berlin")
TODAY = date(2026, 9, 28)  # the stub forecast's first day
# Live answers of Open-Meteo were asked for at this moment (2026-10-05 06:00 UTC).
LIVE = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)


def read(data: dict[str, Any]) -> Forecast:
    return parse(data, "Москва")


def keys(tips: list[Tip]) -> list[str]:
    return [tip.key for tip in tips]


def local(hour: int, minute: int = 0, *, days: int = 0) -> datetime:
    """A wall-clock time of the stub forecast's place, `days` after its first day."""
    return datetime(2026, 9, 28, hour, minute) + timedelta(days=days)


def moment(hour: int, minute: int = 0) -> datetime:
    """An aware moment of the stub forecast's first day, given by the Moscow clock."""
    return datetime(2026, 9, 28, hour, minute, tzinfo=MOSCOW).astimezone(UTC)


GONE = object()  # changed(): the key is removed


def changed(path: tuple[str, ...], value: object) -> dict[str, Any]:
    """The stub answer with one value changed."""
    data = forecast_payload()
    *parents, last = path
    target = data
    for key in parents:
        target = target[key]
    if value is GONE:
        del target[last]
    else:
        target[last] = value
    return data


def test_the_stub_answer_is_one_the_client_keeps() -> None:
    data = forecast_payload()
    assert check_forecast(data) is data
    assert data["current"]["time"] == int(FORECAST_NOW.timestamp())


def test_parse_reads_the_whole_answer() -> None:
    forecast = read(forecast_payload())
    assert (forecast.zone, forecast.tz) == ("Europe/Moscow", MOSCOW)
    assert forecast.now == WeatherNow(
        city="Москва",
        temperature=9.6,
        feels_like=7.2,
        wind=3.4,
        code=1,
        tmin=5.8,
        tmax=13.2,
        tips=[Tip("tip-bike")],
        is_day=True,
        gusts=6.1,
        humidity=71.0,
        precip=0.0,
        at=local(10),
    )
    assert len(forecast.quarters) == 13
    assert forecast.quarters[0] == (local(9, 45), 0.0)
    assert forecast.quarters[-1] == (local(12, 45), 0.0)
    assert len(forecast.hours) == 168
    assert (forecast.hours[0].at, forecast.hours[-1].at) == (local(0), local(23, days=6))
    assert forecast.hours[15] == Hour(
        at=local(15),
        temperature=13.2,
        code=1,
        is_day=True,
        precip_chance=0,
        precip=0.0,
        wind=3.4,
    )
    assert [day.day for day in forecast.days] == [TODAY + timedelta(days=i) for i in range(7)]
    assert forecast.days[1] == Day(
        day=date(2026, 9, 29),
        code=1,
        tmin=5.8,
        tmax=13.2,
        precip_chance=0,
        precip_sum=0.0,
        wind_max=5.2,
        sunrise=local(6, 40, days=1),
        sunset=local(18, 40, days=1),
    )


def test_chances_are_whole_percents_and_a_missing_one_stays_missing() -> None:
    data = forecast_payload()
    data["hourly"]["precipitation_probability"][11:14] = [36.5, None, 0]
    data["daily"]["precipitation_probability_max"][1:3] = [None, 62.4]
    forecast = read(data)
    assert [hour.precip_chance for hour in forecast.hours[11:14]] == [37, None, 0]
    assert [day.precip_chance for day in forecast.days[:3]] == [0, None, 62]


def test_nulls_in_hours_and_days() -> None:
    data = forecast_payload()
    hourly, daily = data["hourly"], data["daily"]
    hourly["temperature_2m"][3] = None  # an hour without a temperature is left out
    for name in ("weather_code", "is_day", "precipitation_probability", "precipitation"):
        hourly[name][4] = None
    hourly["wind_speed_10m"][4] = None
    for name in daily:
        if name != "time":
            daily[name][6] = None  # Open-Meteo's last day may come empty
    daily["temperature_2m_min"][5] = None  # a day without its minimum is left out too
    daily["weather_code"][1] = daily["sunrise"][1] = None
    forecast = read(data)
    assert len(forecast.hours) == 167
    assert forecast.hours[3] == Hour(
        at=local(4),
        temperature=5.9,
        code=-1,
        is_day=True,
        precip_chance=None,
        precip=None,
        wind=None,
    )
    assert describe(forecast.hours[3].code) == ("🌡", "wmo-unknown")
    assert [day.day for day in forecast.days] == [TODAY + timedelta(days=i) for i in range(5)]
    assert (forecast.days[1].code, forecast.days[1].sunrise) == (-1, None)


def test_a_variable_left_out_counts_as_nulls() -> None:
    data = forecast_payload()
    del data["hourly"]["precipitation_probability"]
    del data["daily"]["sunset"]
    forecast = read(data)
    assert len(forecast.hours) == 168 and {hour.precip_chance for hour in forecast.hours} == {None}
    assert len(forecast.days) == 7 and {day.sunset for day in forecast.days} == {None}


def test_moments_that_are_not_times_are_left_out() -> None:
    data = forecast_payload()
    for index, bad in enumerate(("2026-09-28T01:00", None, True, 10**12, -1, float("nan"))):
        data["hourly"]["time"][index] = bad
    data["daily"]["time"][1] = 10**12
    data["daily"]["sunset"][2] = "18:40"
    forecast = read(data)
    assert [hour.at for hour in forecast.hours[:2]] == [local(6), local(7)]
    assert [day.day for day in forecast.days[:2]] == [TODAY, date(2026, 9, 30)]
    assert forecast.days[1].sunset is None


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("minutely_15",), GONE),
        (("current", "time"), None),
        (("current", "temperature_2m"), GONE),
        (("current", "weather_code"), 2.0**80),
        (("hourly", "temperature_2m"), [None] * 168),
        (("hourly", "time"), [1e308] * 168),
        (("hourly", "precipitation_probability"), [1e308] * 168),
        (("daily",), {"time": []}),
        (("timezone",), "Mars/Olympus"),
        (("utc_offset_seconds",), -86399),
    ],
)
def test_parse_reads_whatever_the_client_keeps(path: tuple[str, ...], value: object) -> None:
    data = changed(path, value)
    assert check_forecast(data) is data
    assert read(data).now.tips  # and nothing raised


def test_today_is_the_day_of_the_current_time() -> None:
    # The first day came without its range: today's range is missing, not the next day's.
    data = forecast_payload()
    data["daily"]["temperature_2m_max"][0] = None
    data["daily"]["temperature_2m_max"][1] = 20.0
    now = read(data).now
    assert (now.tmin, now.tmax) == (None, None)


def test_berlin_week_across_the_change_of_clocks() -> None:
    # Asked on 22.10.2026 at 12:00 CEST: Open-Meteo labels the whole week with +02:00, though
    # Berlin goes back to +01:00 on 25.10 at 03:00.
    data = forecast_payload(datetime(2026, 10, 22, 10, 0, tzinfo=UTC), "Europe/Berlin")
    times = data["hourly"]["time"]
    assert data["utc_offset_seconds"] == 7200
    assert data["daily"]["time"] == [1792620000 + k * 86400 for k in range(7)]
    assert times == [1792620000 + k * 3600 for k in range(168)]
    temperatures = data["hourly"]["temperature_2m"]
    temperatures[times.index(1792886400)], temperatures[times.index(1792890000)] = 2.1, 2.2
    forecast = read(data)
    assert forecast.tz == BERLIN
    # The days are 22–28.10: the label 1792965600 is 25.10 23:00 in the zone, yet it is 26.10.
    assert [day.day for day in forecast.days] == [date(2026, 10, 22 + k) for k in range(7)]
    assert datetime.fromtimestamp(1792965600, BERLIN).replace(tzinfo=None) == datetime(
        2026, 10, 25, 23, 0
    )
    assert forecast.days[4].day == date(2026, 10, 26)
    # 25.10 has 25 hours and 02:00 twice: the hours of a day are found by their moment.
    hours = [hour for hour in forecast.hours if hour.at.date() == date(2026, 10, 25)]
    assert len(hours) == 25
    assert [hour.temperature for hour in hours if hour.at.hour == 2] == [2.1, 2.2]
    # The last hour, 1793221200, is 28.10 22:00 by the clock of that day.
    assert times[-1] == 1793221200 and forecast.hours[-1].at == datetime(2026, 10, 28, 22, 0)
    night = datetime(2026, 10, 25, 1, 30)
    assert [hour.at.hour for hour in next_hours(forecast, night, 3)] == [2, 2, 3]
    assert [day.day for day in days_from(forecast, date(2026, 10, 26))] == [
        date(2026, 10, 26),
        date(2026, 10, 27),
        date(2026, 10, 28),
    ]


def test_an_unknown_zone_falls_back_to_the_offset() -> None:
    data = forecast_payload()
    data["timezone"] = "Mars/Olympus"
    forecast = read(data)
    assert (forecast.zone, forecast.tz) == ("Mars/Olympus", timezone(timedelta(hours=3)))
    assert (forecast.now.at, forecast.hours[0].at) == (local(10), local(0))
    assert local_now(forecast, FORECAST_NOW) == local(10)


def test_polar_night_and_day() -> None:
    # As Open-Meteo answered on 05.10.2026: near the North Pole both the sunrise and the sunset
    # are the day's 00:00, at McMurdo the sunrise is 00:00 and the sunset the next 00:00.
    north = forecast_payload(LIVE, "Etc/GMT")
    assert north["daily"]["time"][0] == 1791158400
    north["daily"]["sunrise"][0] = north["daily"]["sunset"][0] = 1791158400
    south = forecast_payload(LIVE, "Antarctica/McMurdo")
    assert south["daily"]["time"][:2] == [1791111600, 1791198000]
    south["daily"]["sunrise"][0], south["daily"]["sunset"][0] = 1791111600, 1791198000
    night, day = read(north).days[0], read(south).days[0]
    assert night.sunrise == night.sunset == datetime(2026, 10, 5)
    assert (day.sunrise, day.sunset) == (datetime(2026, 10, 5), datetime(2026, 10, 6))
    assert (polar(night), polar(day)) == ("night", "day")
    assert polar(read(forecast_payload()).days[0]) is None  # 06:40 and 18:40
    assert polar(replace(day, sunset=None)) is None


def test_describe_codes() -> None:
    assert describe(0) == ("☀️", "wmo-clear")
    assert describe(63) == ("🌧", "wmo-rain")
    assert describe(96) == ("⛈", "wmo-storm")
    assert describe(1234) == describe(4) == describe(-1) == ("🌡", "wmo-unknown")
    assert translator("ru")("wmo-unknown") == "нет данных"
    assert translator("en")("wmo-unknown") == "no data"


def test_night_icons() -> None:
    assert [describe(code, is_day=False) for code in (0, 1, 2)] == [
        ("🌙", "wmo-clear"),
        ("🌙", "wmo-partly"),
        ("🌙", "wmo-partly"),
    ]
    assert describe(3, is_day=False) == ("☁️", "wmo-cloudy")
    assert describe(61, is_day=False) == ("🌧", "wmo-rain")
    assert describe(-1, is_day=False) == ("🌡", "wmo-unknown")
    forecast = read(forecast_payload(is_day=0))
    assert forecast.now.is_day is False
    assert [hour.is_day for hour in forecast.hours[5:9]] == [False, False, True, True]
    assert read(forecast_payload(is_day=None)).now.is_day is True


# Tips


def test_rain_in_45_minutes() -> None:
    # The quarter-hours start at 09:45; the fifth, at 10:45, is wet.
    tips = read(forecast_payload(quarters=[0, 0, 0, 0, 0.6])).now.tips
    assert tips[0] == Tip("tip-precip-soon", {"kind": "rain", "minutes": 45})


def test_rain_soon_counts_only_the_quarters_ahead_in_kathmandu() -> None:
    # Asia/Kathmandu (+05:45) as Open-Meteo answered: 13 quarter-hours from an hour before
    # `current` (11:45) to two hours after it. It is wet already, but the quarters before now
    # and now itself are not «soon».
    wet = [0.0, 0.2, 0.2, 0.2, 0.2, 0.3, 0.3, 0.3, 0.3, 0.1, 0.1, 0.1, 0.1]
    data = forecast_payload(LIVE, "Asia/Kathmandu", quarters=wet, quarters_from=-60)
    assert data["current"]["time"] == 1791180000
    assert data["minutely_15"]["time"][::12] == [1791176400, 1791187200]
    forecast = read(data)
    assert forecast.now.at == datetime(2026, 10, 5, 11, 45)
    assert (forecast.quarters[0][0], forecast.quarters[-1][0]) == (
        datetime(2026, 10, 5, 10, 45),
        datetime(2026, 10, 5, 13, 45),
    )
    assert forecast.now.tips[0] == Tip("tip-precip-soon", {"kind": "rain", "minutes": 15})


def test_rain_soon_looks_two_hours_ahead_in_st_johns() -> None:
    # America/St_Johns (−02:30) as Open-Meteo answered: 13 quarter-hours from 15 to 195
    # minutes after `current` (03:30). Only the first two hours count.
    def wet_at(minutes: int) -> list[float]:
        return [0.4 if 15 + 15 * step == minutes else 0.0 for step in range(13)]

    late = forecast_payload(LIVE, "America/St_Johns", quarters=wet_at(135), quarters_from=15)
    assert late["minutely_15"]["time"][::12] == [1791180900, 1791191700]
    forecast = read(late)
    assert forecast.quarters[-1][0] == datetime(2026, 10, 5, 6, 45)
    assert "tip-precip-soon" not in keys(forecast.now.tips)
    edge = forecast_payload(LIVE, "America/St_Johns", quarters=wet_at(120), quarters_from=15)
    assert read(edge).now.tips[0] == Tip("tip-precip-soon", {"kind": "rain", "minutes": 120})


def test_snow_now_with_frost_and_wind() -> None:
    data = forecast_payload(temperature=-18, feels_like=-25, precip=0.4, wind=12)
    tips = read(data).now.tips
    assert keys(tips)[:1] == ["tip-precip-now"] and tips[0].params == {"kind": "snow"}
    assert {"tip-wind", "tip-frost"} <= set(keys(tips))


def test_snow_later_uses_snow_kind() -> None:
    data = forecast_payload(temperature=-2)
    data["hourly"]["precipitation_probability"][17] = 80  # the label 17:00: 16:00–17:00
    assert read(data).now.tips[0] == Tip("tip-precip-later", {"kind": "snow", "hour": "16:00"})


def test_rain_later_names_the_hour_its_chance_is_about() -> None:
    # Now is 10:00, and a chance is about the hour before its label.
    data = forecast_payload()
    data["hourly"]["precipitation_probability"][12] = 90  # 11:00–12:00
    assert read(data).now.tips[0] == Tip("tip-precip-later", {"kind": "rain", "hour": "11:00"})
    data = forecast_payload()
    data["hourly"]["precipitation_probability"][11] = 90  # 10:00–11:00 starts now: not later
    assert "tip-precip-later" not in keys(read(data).now.tips)


def test_rain_later_is_about_the_rest_of_today_only() -> None:
    data = forecast_payload()
    chances = data["hourly"]["precipitation_probability"]
    chances[9] = chances[10] = chances[11] = 90  # about 08:00–11:00: not after 10:00
    chances[24 + 11] = 90  # tomorrow
    assert "tip-precip-later" not in keys(read(data).now.tips)


def test_missing_minutely_block_is_fine() -> None:
    forecast = read(forecast_payload(quarters=None))
    assert forecast.quarters == [] and "tip-precip-soon" not in keys(forecast.now.tips)


def test_none_values_do_not_crash() -> None:
    data = forecast_payload(temperature=None, feels_like=None, wind=None, precip=None)
    data["daily"]["temperature_2m_max"][0] = None
    assert read(data).now.tips  # at least the calm tip or an evening tip


def test_bike_day_and_warmer_evening() -> None:
    data = forecast_payload()
    data["hourly"]["temperature_2m"][8], data["hourly"]["temperature_2m"][18] = 6, 14
    data["daily"]["temperature_2m_max"][0] = 16
    assert keys(read(data).now.tips) == ["tip-warmer-evening", "tip-bike"]


def test_colder_evening() -> None:
    data = forecast_payload()
    data["hourly"]["temperature_2m"][8], data["hourly"]["temperature_2m"][18] = 14, 8
    assert keys(read(data).now.tips) == ["tip-colder-evening", "tip-bike"]


def test_calm_when_nothing_special() -> None:
    data = forecast_payload()
    data["daily"]["temperature_2m_min"][0], data["daily"]["temperature_2m_max"][0] = 1, 5
    assert keys(read(data).now.tips) == ["tip-calm"]


def test_malformed_current_time_counts_as_missing() -> None:
    for bad in ("2026-09-28T10:00", None, True, 10**12, -1, float("nan")):
        data = forecast_payload()
        data["current"]["time"] = bad
        now = read(data).now
        assert now.at is None and now.tips == [Tip("tip-calm")]


def test_malformed_minutely_and_hourly_entries_are_skipped() -> None:
    data = forecast_payload(quarters=[0, 0, 0, 0.6, 0.6])
    data["minutely_15"]["time"][3] = "10:30 today"
    data["hourly"]["time"][3] = "garbage"
    data["hourly"]["time"][4] = None
    forecast = read(data)
    # The broken 10:30 step is left out; the next one (10:45) still gives the tip.
    assert forecast.now.tips[0] == Tip("tip-precip-soon", {"kind": "rain", "minutes": 45})
    assert len(forecast.quarters) == 4 and len(forecast.hours) == 166


async def test_current_with_malformed_time_still_reports_the_weather() -> None:
    data = forecast_payload(temperature=10)
    data["current"]["time"] = "yesterday"

    class Meteo:
        async def forecast(self, lat: float, lon: float) -> dict[str, Any]:
            return data

    now = await current(Meteo(), "Москва", 55.75, 37.62)
    # Without the time of `current` the first day stands for today.
    assert (now.temperature, now.tmax, now.tips) == (10.0, 13.2, [Tip("tip-calm")])


def _drop_current(data: dict[str, Any]) -> None:
    del data["current"]


def _break_hourly(data: dict[str, Any]) -> None:
    data["hourly"] = [1]


def _nan_temperature(data: dict[str, Any]) -> None:
    data["current"]["temperature_2m"] = float("nan")


@pytest.mark.parametrize("damage", [_drop_current, _break_hourly, _nan_temperature])
async def test_an_answer_without_current_or_with_a_broken_block_is_an_error(
    damage: Callable[[dict[str, Any]], None],
) -> None:
    # It used to give a forecast of nothing and «👌 Погода без сюрпризов».
    data = forecast_payload()
    damage(data)
    answer = json.dumps(data)  # NaN goes as the bare token NaN, which Python's json reads

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=answer)

    meteo = OpenMeteoClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(UpstreamUnavailable):
        await weather.forecast(meteo, "Москва", 55.75, 37.62)


async def test_forecast_and_current_read_one_answer_each() -> None:
    asked: list[tuple[float, float]] = []

    class Meteo:
        async def forecast(self, lat: float, lon: float) -> dict[str, Any]:
            asked.append((lat, lon))
            return forecast_payload()

    forecast = await weather.forecast(Meteo(), "Тула", 54.19, 37.62)
    assert forecast.now.city == "Тула" and len(forecast.days) == 7
    assert await current(Meteo(), "Тула", 54.19, 37.62) == forecast.now
    assert asked == [(54.19, 37.62), (54.19, 37.62)]


# Time helpers


def test_local_now_is_the_wall_clock_of_the_place() -> None:
    assert local_now(read(forecast_payload()), FORECAST_NOW) == local(10)
    tokyo = read(forecast_payload(zone="Asia/Tokyo"))
    assert local_now(tokyo, FORECAST_NOW) == local(16)
    with pytest.raises(ValueError):
        local_now(tokyo, datetime(2026, 9, 28, 7, 0))


def test_next_hours_start_after_now() -> None:
    forecast = read(forecast_payload())
    assert [hour.at for hour in next_hours(forecast, local(10), 3)] == [
        local(11),
        local(12),
        local(13),
    ]
    assert next_hours(forecast, local(10, 20), 1)[0].at == local(11)
    assert len(next_hours(forecast, local(10), 12)) == 12
    assert [hour.at for hour in next_hours(forecast, local(21, days=6), 12)] == [
        local(22, days=6),
        local(23, days=6),
    ]
    assert next_hours(forecast, local(23, days=6), 12) == []


def test_days_from_today() -> None:
    forecast = read(forecast_payload())
    assert [day.day for day in days_from(forecast, TODAY)] == [
        TODAY + timedelta(days=i) for i in range(7)
    ]
    assert len(days_from(forecast, TODAY, 3)) == 3
    # Just after midnight a forecast kept from yesterday starts a day early: six days are left.
    assert [day.day for day in days_from(forecast, TODAY + timedelta(days=1))] == [
        TODAY + timedelta(days=i) for i in range(1, 7)
    ]


def test_hour_of_a_moment() -> None:
    forecast = read(forecast_payload())
    assert hour_of(forecast, local(9)) == forecast.hours[9]
    assert hour_of(forecast, local(16, 20)) == forecast.hours[16]
    assert hour_of(forecast, local(23, 59, days=6)) == forecast.hours[-1]
    assert hour_of(forecast, local(0, days=7)) is None
    assert hour_of(forecast, local(23, 59, days=-1)) is None


def test_chance_after_takes_the_label_rounded_up() -> None:
    # A label's chance is that of the hour before it: 16:00 tells about 15:00–16:00.
    data = forecast_payload()
    chances = data["hourly"]["precipitation_probability"]
    chances[9], chances[16], chances[17] = 70, 10, 40
    forecast = read(data)
    assert chance_after(forecast, local(9)) == 70  # the hour 08:00–09:00
    assert chance_after(forecast, local(16)) == 10
    assert chance_after(forecast, local(16, 20)) == 40  # the label 17:00
    assert chance_after(forecast, local(23, 30, days=6)) is None  # no label after the week


def test_tomorrow() -> None:
    forecast = read(forecast_payload())
    following = tomorrow(forecast, TODAY)
    assert following is not None and following.day == date(2026, 9, 29)
    assert tomorrow(forecast, date(2026, 10, 4)) is None


def test_classes_weather_takes_the_hours_of_the_way() -> None:
    # Classes from 09:00 to 16:20: the temperatures at 09:00 and at 16:00, the chances of the
    # way there (08:00–09:00, label 09:00) and of the way home (16:20–17:00, label 17:00).
    data = forecast_payload()
    hourly = data["hourly"]
    hourly["temperature_2m"][9], hourly["temperature_2m"][16] = 3.0, 6.0
    hourly["precipitation_probability"][9] = 70
    hourly["precipitation_probability"][16] = 90  # still in class
    hourly["precipitation_probability"][17] = 70
    found = classes_weather(read(data), moment(9), moment(16, 20), "Europe/Moscow")
    assert found == ClassesWeather(
        start=local(9),
        start_temp=3.0,
        start_chance=70,
        end=local(16, 20),
        end_temp=6.0,
        end_chance=70,
    )


def test_classes_weather_leaves_out_a_chance_under_30() -> None:
    data = forecast_payload()
    data["hourly"]["precipitation_probability"][9] = 29
    data["hourly"]["precipitation_probability"][17] = 30
    found = classes_weather(read(data), moment(9), moment(16, 20), "Europe/Moscow")
    assert found is not None and (found.start_chance, found.end_chance) == (None, 30)


def test_classes_weather_without_an_hour_for_the_start_or_the_end() -> None:
    data = forecast_payload()
    data["hourly"]["temperature_2m"][9] = None
    data["hourly"]["precipitation_probability"][10] = 80
    found = classes_weather(read(data), moment(9, 30), moment(16, 20), "Europe/Moscow")
    # No hour for the start: no «to classes» part, its chance included.
    assert found is not None and (found.start_temp, found.start_chance) == (None, None)
    assert (found.end, found.end_temp) == (local(16, 20), 13.0)
    data["hourly"]["temperature_2m"][16] = None  # no hour for the end: no line
    assert classes_weather(read(data), moment(9), moment(16, 20), "Europe/Moscow") is None


def test_classes_weather_finds_the_hours_on_the_clock_of_the_forecast() -> None:
    # The user's zone is Moscow, the home city's forecast comes in Yekaterinburg's time
    # (+05:00): classes at 09:00 Moscow time are at 11:00 there, and the line shows 09:00.
    data = forecast_payload(zone="Asia/Yekaterinburg")
    data["hourly"]["temperature_2m"][11] = 2.0
    found = classes_weather(read(data), moment(9), moment(16, 20), "Europe/Moscow")
    assert found is not None
    assert (found.start, found.start_temp, found.end, found.end_temp) == (
        local(9),
        2.0,
        local(16, 20),
        11.6,
    )
