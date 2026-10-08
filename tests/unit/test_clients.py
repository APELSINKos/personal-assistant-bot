from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
import pytest

from assistant.core.clients.cbr import CbrClient, Point
from assistant.core.clients.openmeteo import City, OpenMeteoClient, check_forecast
from assistant.core.errors import UpstreamUnavailable

CBR = {
    "Date": "2026-09-28T11:30:00+03:00",
    "Valute": {
        "USD": {"Nominal": 1, "Value": 84.1975, "Previous": 84.5093},
        "EUR": {"Nominal": 1, "Value": 96.6671, "Previous": 97.4984},
    },
}


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_cbr_parses_and_caches() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=CBR)

    cbr = CbrClient(client(handler))
    rates = await cbr.daily()
    await cbr.daily()
    assert calls == 1
    assert rates.day == date(2026, 9, 28)
    assert round(rates.usd.value, 4) == 84.1975 and round(rates.usd.change, 4) == -0.3118


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"Valute": {}}),
    ],
)
async def test_cbr_errors_become_upstream_unavailable(response: httpx.Response) -> None:
    with pytest.raises(UpstreamUnavailable):
        await CbrClient(client(lambda request: response)).daily()


async def test_cbr_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(UpstreamUnavailable):
        await CbrClient(client(handler)).daily()


CBR_ALL = {
    "Date": "2026-10-03T11:30:00+03:00",
    "Valute": {
        "USD": {"ID": "R01235", "Nominal": 1, "Value": 83.4839, "Previous": 83.2454},
        "EUR": {"ID": "R01239", "Nominal": 1, "Value": 94.3201, "Previous": 94.5252},
        "AMD": {"ID": "R01060", "Nominal": 100, "Value": 21.5, "Previous": 21.4},
        "XXX": {"ID": "R0", "Nominal": 0, "Value": 1, "Previous": 1},
    },
}
HISTORY = (
    '<?xml version="1.0" encoding="windows-1251"?>'
    '<ValCurs ID="R01235" DateRange1="03.09.2026" DateRange2="03.10.2026" name="Динамика">'
    '<Record Date="03.10.2026" Id="R01235"><Nominal>1</Nominal><Value>83,4839</Value>'
    "<VunitRate>83,4839</VunitRate></Record>"
    '<Record Date="02.10.2026" Id="R01235"><Nominal>1</Nominal><Value>83,2454</Value>'
    "<VunitRate>83,2454</VunitRate></Record>"
    "</ValCurs>"
).encode("cp1251")


async def test_cbr_gives_every_currency_of_the_day_per_unit() -> None:
    rates = await CbrClient(client(lambda request: httpx.Response(200, json=CBR_ALL))).daily()
    assert sorted(rates.currencies) == ["AMD", "EUR", "USD"]  # the odd one is left out
    assert round(rates.currencies["AMD"].value, 4) == 0.215  # Nominal 100
    assert rates.ids["USD"] == "R01235"
    assert rates.usd == rates.currencies["USD"]


async def test_cbr_history_over_30_days_cached() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "www.cbr.ru":
            return httpx.Response(200, content=HISTORY)
        return httpx.Response(200, json=CBR_ALL)

    cbr = CbrClient(client(handler))
    points = await cbr.history("USD")
    assert points == [Point(date(2026, 10, 2), 83.2454), Point(date(2026, 10, 3), 83.4839)]
    assert await cbr.history("USD") == points
    asked = [request for request in seen if request.url.host == "www.cbr.ru"]
    assert len(asked) == 1
    assert dict(asked[0].url.params) == {
        "date_req1": "03/09/2026", "date_req2": "03/10/2026", "VAL_NM_RQ": "R01235",
    }  # fmt: skip
    with pytest.raises(LookupError):
        await cbr.history("GBP")


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500),
        httpx.Response(200, content=b"<html>not xml"),
        httpx.Response(200, content=b'<!DOCTYPE x [<!ENTITY a "a">]><ValCurs/>'),
        httpx.Response(200, content=b"<ValCurs>" + b" " * 300_000 + b"</ValCurs>"),
        httpx.Response(200, content=HISTORY.replace(b"83,4839", b"oops")),
        httpx.Response(200, content=b'<ValCurs ID="R01235"/>'),  # no Record: not kept, asked again
    ],
)
async def test_cbr_history_errors_become_upstream_unavailable(answer: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return answer if request.url.host == "www.cbr.ru" else httpx.Response(200, json=CBR_ALL)

    with pytest.raises(UpstreamUnavailable):
        await CbrClient(client(handler)).history("USD")


# A live answer's current quarter-hour (2026-10-05 10:45 in Moscow) and that day's 00:00 there.
NOW = 1791186300
MIDNIGHT = 1791147600
QUICK = 0.1  # seconds: a deadline the tests wait out
GONE = object()  # changed(): the key is removed
FORECAST_QUERY = {
    "latitude": "55.75",
    "longitude": "37.62",
    "timezone": "auto",
    "timeformat": "unixtime",
    "wind_speed_unit": "ms",
    "forecast_days": "7",
    "past_minutely_15": "1",
    "forecast_minutely_15": "12",
    "current": "temperature_2m,apparent_temperature,weather_code,is_day,wind_speed_10m,"
    "wind_gusts_10m,relative_humidity_2m,precipitation",
    "minutely_15": "precipitation",
    "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code,is_day,"
    "wind_speed_10m",
    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
    "precipitation_sum,wind_speed_10m_max,sunrise,sunset",
}


def payload() -> dict[str, Any]:
    """A valid answer to the client's forecast request, cut to a few steps."""
    return {
        "latitude": 55.75,
        "longitude": 37.625,
        "utc_offset_seconds": 10800,
        "timezone": "Europe/Moscow",
        "current": {
            "time": NOW,
            "interval": 900,
            "temperature_2m": 11.1,
            "apparent_temperature": 9.8,
            "weather_code": 3,
            "is_day": 1,
            "wind_speed_10m": 1.94,
            "wind_gusts_10m": 5.4,
            "relative_humidity_2m": 85,
            "precipitation": 0.0,
        },
        "minutely_15": {"time": [NOW - 900, NOW, NOW + 900], "precipitation": [0.0, 0.0, 0.2]},
        "hourly": {
            "time": [NOW - 2700, NOW + 900, NOW + 4500],  # 10:00, 11:00, 12:00
            "temperature_2m": [10.4, 11.1, 12.0],
            "precipitation_probability": [3, 5, None],
            "precipitation": [0.0, 0.0, 0.1],
            "weather_code": [3, 3, 61],
            "is_day": [1, 1, 1],
            "wind_speed_10m": [1.8, 1.94, 2.5],
        },
        "daily": {
            "time": [MIDNIGHT, MIDNIGHT + 86400],
            "weather_code": [61, 3],
            "temperature_2m_max": [13.0, None],  # Open-Meteo's last day may come empty
            "temperature_2m_min": [8.7, None],
            "precipitation_probability_max": [70, None],
            "precipitation_sum": [0.9, None],
            "wind_speed_10m_max": [2.31, None],
            "sunrise": [1791171594, None],
            "sunset": [1791212090, None],
        },
    }


def changed(path: tuple[str, ...], value: object) -> dict[str, Any]:
    """payload() with the key at `path` set to `value`, or removed when `value` is GONE."""
    data = payload()
    *blocks, key = path
    target = data
    for block in blocks:
        target = target[block]
    if value is GONE:
        del target[key]
    else:
        target[key] = value
    return data


def open_meteo(
    answer: Callable[[httpx.Request], Any], **options: Any
) -> tuple[OpenMeteoClient, list[httpx.Request]]:
    """A client whose requests `answer` (plain or async) answers, and the list of those requests."""
    asked: list[httpx.Request] = []

    def handler(request: httpx.Request) -> Any:
        asked.append(request)
        return answer(request)

    return OpenMeteoClient(client(handler), **options), asked


def forecast_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=payload())


def refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


def timed_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


def bank(answer: Callable[[httpx.Request], Any], **options: Any) -> tuple[CbrClient, list[str]]:
    """A bank client whose requests `answer` (plain or async) answers, and the paths it asked."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> Any:
        asked.append(request.url.path)
        return answer(request)

    return CbrClient(client(handler), **options), asked


@pytest.mark.parametrize("failure", [timed_out, refused], ids=["timeout", "network"])
async def test_cbr_a_network_failure_pauses_the_rates_for_a_minute(
    failure: Callable[[httpx.Request], httpx.Response],
) -> None:
    now = [0.0]
    failures = [failure]

    def answer(request: httpx.Request) -> httpx.Response:
        return failures.pop()(request) if failures else httpx.Response(200, json=CBR)

    cbr, asked = bank(answer, clock=lambda: now[0])
    with pytest.raises(UpstreamUnavailable):
        await cbr.daily()
    now[0] = 59.9
    with pytest.raises(UpstreamUnavailable):  # not even asked
        await cbr.daily()
    assert len(asked) == 1
    now[0] = 60.0
    assert round((await cbr.daily()).usd.value, 4) == 84.1975
    assert len(asked) == 2


async def test_cbr_an_answer_that_came_opens_no_pause() -> None:
    # It came at once: one quick 503 at 08:00 must not cost every digest of that minute its rates.
    answers = iter(
        [httpx.Response(503), httpx.Response(200, text="not json"), httpx.Response(200, json=CBR)]
    )
    cbr, asked = bank(lambda request: next(answers))
    for _ in range(2):
        with pytest.raises(UpstreamUnavailable):
            await cbr.daily()
    assert round((await cbr.daily()).usd.value, 4) == 84.1975
    assert len(asked) == 3


async def test_cbr_an_answer_slower_than_the_deadline_is_cut() -> None:
    async def answer(request: httpx.Request) -> httpx.Response:
        # A mirror that sends a byte now and then runs out no timeout of httpx's phases.
        await asyncio.sleep(10)
        return httpx.Response(200, json=CBR)

    cbr, asked = bank(answer, deadline=QUICK)
    with pytest.raises(UpstreamUnavailable):
        await asyncio.wait_for(cbr.daily(), 2)
    with pytest.raises(UpstreamUnavailable):  # not even asked
        await asyncio.wait_for(cbr.daily(), 1)
    assert len(asked) == 1


async def test_cbr_a_hanging_history_pauses_histories_not_the_rates() -> None:
    now = [0.0]

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.cbr.ru":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=CBR_ALL)

    # The day's rates are kept for 10 s here, so the second history asks for them again.
    cbr, asked = bank(answer, ttl=10.0, clock=lambda: now[0])
    with pytest.raises(UpstreamUnavailable):
        await cbr.history("EUR")
    now[0] = 30.0
    with pytest.raises(UpstreamUnavailable):  # the mirror is asked, cbr.ru is not
        await cbr.history("EUR")
    assert asked == ["/daily_json.js", "/scripts/XML_dynamic.asp", "/daily_json.js"]


async def test_openmeteo_forecast_asks_once_per_place_with_rounded_coordinates() -> None:
    om, asked = open_meteo(forecast_ok)
    data = await om.forecast(55.75204, 37.61781)
    assert await om.forecast(55.7512, 37.6249) is data  # the same 0.01° cell
    [request] = asked
    assert (request.url.host, request.url.path) == ("api.open-meteo.com", "/v1/forecast")
    # Open-Meteo keeps its logs for 90 days: it gets the rounded coordinates too.
    assert dict(request.url.params) == FORECAST_QUERY
    blocks = ("current", "minutely_15", "hourly", "daily")
    assert sum(len(FORECAST_QUERY[block].split(",")) for block in blocks) == 23


async def test_openmeteo_forecast_is_kept_for_ten_minutes() -> None:
    now = [0.0]
    om, asked = open_meteo(forecast_ok, clock=lambda: now[0])
    await om.forecast(55.75, 37.62)
    now[0] = 599.9
    await om.forecast(55.75, 37.62)
    assert len(asked) == 1
    now[0] = 600.0
    await om.forecast(55.75, 37.62)
    assert len(asked) == 2


async def test_openmeteo_keeps_512_places_and_drops_the_oldest() -> None:
    om, asked = open_meteo(forecast_ok)
    for step in range(512):
        await om.forecast(step / 100, 0.0)
    await om.forecast(0.0, 0.0)  # reading the oldest does not make it younger
    await om.forecast(5.12, 0.0)  # the 513th place
    await om.forecast(0.01, 0.0)  # the second one is still kept
    assert len(asked) == 513
    await om.forecast(0.0, 0.0)  # the first one has gone
    assert len(asked) == 514


async def test_openmeteo_asks_for_two_forecasts_at_a_time() -> None:
    running = most = 0

    async def answer(request: httpx.Request) -> httpx.Response:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.01)
        running -= 1
        return forecast_ok(request)

    om, asked = open_meteo(answer)
    await asyncio.gather(*(om.forecast(lat, 0.0) for lat in (10.0, 20.0, 30.0, 40.0, 50.0)))
    assert (most, len(asked)) == (2, 5)


async def test_openmeteo_a_call_that_waited_takes_what_the_call_before_fetched() -> None:
    async def answer(request: httpx.Request) -> httpx.Response:
        # The first place answers sooner, so its slot goes to the call that waits for it again.
        await asyncio.sleep(0.01 if request.url.params["latitude"] == "10.0" else 0.05)
        return forecast_ok(request)

    om, asked = open_meteo(answer)
    first, _, again = await asyncio.gather(
        om.forecast(10.0, 0.0), om.forecast(20.0, 0.0), om.forecast(10.0, 0.0)
    )
    assert again is first
    assert sorted(request.url.params["latitude"] for request in asked) == ["10.0", "20.0"]


async def test_openmeteo_calls_waiting_behind_a_failure_do_not_go_out() -> None:
    async def answer(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.01)
        return httpx.Response(503)

    om, asked = open_meteo(answer)
    calls = [om.forecast(lat, 0.0) for lat in (10.0, 20.0, 30.0, 40.0)]
    results = await asyncio.gather(*calls, return_exceptions=True)
    assert all(isinstance(result, UpstreamUnavailable) for result in results)
    assert len(asked) == 2  # only the two that had the slots


@pytest.mark.parametrize(
    "failure",
    [
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(503, json={"error": True, "reason": "overloaded"}),
        lambda request: httpx.Response(429, json={"error": True, "reason": "Too many requests"}),
        lambda request: httpx.Response(200, text="not json"),
        lambda request: httpx.Response(200, json=changed(("hourly",), GONE)),
        # httpx refuses NaN in json=, so Python's json writes this body: it allows NaN.
        lambda request: httpx.Response(
            200, text=json.dumps(changed(("current", "temperature_2m"), math.nan))
        ),
        refused,
        timed_out,
    ],
    ids=["500", "503", "429", "not json", "no hourly", "NaN", "network", "timeout"],
)
async def test_openmeteo_failure_pauses_forecasts_for_a_minute(
    failure: Callable[[httpx.Request], httpx.Response],
) -> None:
    now = [0.0]
    failures = [failure]

    def answer(request: httpx.Request) -> httpx.Response:
        return failures.pop()(request) if failures else forecast_ok(request)

    om, asked = open_meteo(answer, clock=lambda: now[0])
    with pytest.raises(UpstreamUnavailable):
        await om.forecast(55.75, 37.62)
    now[0] = 59.9
    with pytest.raises(UpstreamUnavailable):  # not even asked
        await om.forecast(59.94, 30.31)
    assert len(asked) == 1
    now[0] = 60.0
    await om.forecast(55.75, 37.62)  # asked again: the failed answer was not kept
    assert len(asked) == 2


async def test_openmeteo_deadline_inside_the_exchange_pauses_forecasts() -> None:
    async def answer(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return forecast_ok(request)

    om, asked = open_meteo(answer, deadline=QUICK)
    with pytest.raises(UpstreamUnavailable):
        await om.forecast(55.75, 37.62)
    with pytest.raises(UpstreamUnavailable):  # not even asked
        await om.forecast(59.94, 30.31)
    assert len(asked) == 1


async def test_openmeteo_deadline_in_the_queue_opens_no_pause() -> None:
    om, asked = open_meteo(forecast_ok, deadline=QUICK)
    async with om._slots, om._slots:  # both slots are busy
        with pytest.raises(UpstreamUnavailable):
            # Without the deadline over the queue the call would never get a slot: the test
            # holds both until it returns.
            await asyncio.wait_for(om.forecast(55.75, 37.62), 2)
    assert asked == []
    await om.forecast(55.75, 37.62)
    assert len(asked) == 1


@pytest.mark.parametrize("status", [400, 404])
async def test_openmeteo_client_errors_do_not_pause(status: int) -> None:
    om, asked = open_meteo(
        lambda request: httpx.Response(status, json={"error": True, "reason": "Invalid timezone"})
    )
    for _ in range(2):
        with pytest.raises(UpstreamUnavailable):
            await om.forecast(55.75, 37.62)
    assert len(asked) == 2


async def test_openmeteo_serves_fresh_forecasts_during_the_pause() -> None:
    now = [0.0]

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.params["latitude"] == "59.94":
            return httpx.Response(503)
        return forecast_ok(request)

    om, asked = open_meteo(answer, clock=lambda: now[0])
    kept = await om.forecast(55.75, 37.62)
    with pytest.raises(UpstreamUnavailable):
        await om.forecast(59.94, 30.31)
    now[0] = 30.0
    assert await om.forecast(55.75, 37.62) is kept
    assert len(asked) == 2


async def test_openmeteo_checks_the_cache_and_the_pause_before_the_queue() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.params["latitude"] == "59.94":
            return httpx.Response(503)
        return forecast_ok(request)

    om, asked = open_meteo(answer)
    kept = await om.forecast(55.75, 37.62)
    with pytest.raises(UpstreamUnavailable):
        await om.forecast(59.94, 30.31)  # forecasts are paused now
    async with om._slots, om._slots:  # and both slots are busy
        # The deadline is 10 s: a call that waited for a slot first would not end within 1 s.
        assert await asyncio.wait_for(om.forecast(55.75, 37.62), 1) is kept
        with pytest.raises(UpstreamUnavailable):
            await asyncio.wait_for(om.forecast(43.12, 131.89), 1)
    assert len(asked) == 2


async def test_openmeteo_an_answer_ends_the_pause() -> None:
    async def answer(request: httpx.Request) -> httpx.Response:
        # Both are asked at once; the second one answers after the first has failed.
        if request.url.params["latitude"] == "59.94":
            await asyncio.sleep(0.01)
            return httpx.Response(503)
        await asyncio.sleep(0.05)
        return forecast_ok(request)

    om, asked = open_meteo(answer)
    failed, answered = await asyncio.gather(
        om.forecast(59.94, 30.31), om.forecast(55.75, 37.62), return_exceptions=True
    )
    assert isinstance(failed, UpstreamUnavailable) and isinstance(answered, dict)
    await om.forecast(43.12, 131.89)
    assert len(asked) == 3


def test_check_forecast_takes_an_answer_as_it_comes() -> None:
    data = payload()
    assert check_forecast(data) is data


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("minutely_15",), GONE),  # no «rain soon» then
        (("hourly", "precipitation_probability"), GONE),  # a variable left out is all nulls
        (("current", "temperature_2m"), GONE),
        (("current", "time"), None),
        (("hourly", "temperature_2m"), [None, None, None]),
        (("daily",), {"time": []}),
        (("utc_offset_seconds",), 20700),  # Kathmandu
        (("utc_offset_seconds",), -86399),
        (("timezone",), "Mars/Olympus"),  # the parser falls back to the offset
        (("hourly", "snowfall"), ["not asked for"]),  # what was not asked for is not looked at
    ],
)
def test_check_forecast_takes_nulls_and_gaps(path: tuple[str, ...], value: object) -> None:
    data = changed(path, value)
    assert check_forecast(data) is data


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("timezone",), GONE),
        (("timezone",), ""),
        (("timezone",), 3),
        (("utc_offset_seconds",), GONE),
        (("utc_offset_seconds",), 10800.0),
        (("utc_offset_seconds",), True),
        (("utc_offset_seconds",), 86400),
        (("utc_offset_seconds",), -86400),
        (("current",), GONE),
        (("current",), [1]),
        (("hourly",), GONE),
        (("daily",), None),
        (("minutely_15",), "precipitation"),
        (("hourly", "time"), GONE),
        (("daily", "time"), MIDNIGHT),
        (("daily", "sunrise"), 1791171594),
        (("hourly", "temperature_2m"), [10.4, 11.1]),
        (("hourly", "weather_code"), [3, 3, 61, 61]),
        (("hourly", "temperature_2m"), [10.4, math.nan, 12.0]),
        (("current", "temperature_2m"), math.inf),
        (("minutely_15", "time"), [NOW - 900, NOW, -math.inf]),
        (("hourly", "precipitation"), [0.0, 0.0, 10**400]),  # no float holds it
        (("daily", "weather_code"), [61, "3"]),
        (("hourly", "time"), ["2026-10-05T10:00", "2026-10-05T11:00", "2026-10-05T12:00"]),
        (("hourly", "is_day"), [1, True, 1]),
        (("current", "weather_code"), [3]),
    ],
)
def test_check_forecast_refuses_a_wrong_shape(path: tuple[str, ...], value: object) -> None:
    with pytest.raises(ValueError):
        check_forecast(changed(path, value))


def test_check_forecast_refuses_what_is_not_an_object() -> None:
    for data in ([payload()], "forecast", None):
        with pytest.raises(ValueError):
            check_forecast(data)


SPB = {
    "id": 498817,
    "name": "Санкт-Петербург",
    "latitude": 59.93863,
    "longitude": 30.31413,
    "feature_code": "PPLA",
    "country_code": "RU",
    "admin1": "Санкт-Петербург",
    "timezone": "Europe/Moscow",
    "country": "Россия",
}
PARIS = {
    "id": 2988507,
    "name": "Paris",
    "latitude": 48.85341,
    "longitude": 2.3488,
    "admin1": "Île-de-France",
    "timezone": "Europe/Paris",
    "country": "France",
}
# What the geocoder finds by the exact text: hyphens matter, and a qualifier after the comma
# that it does not know hides everything.
PLACES = {"Санкт-Петербург": [SPB], "Санкт-Петербург, Россия": [SPB], "Paris": [PARIS]}


def geocoder(request: httpx.Request) -> httpx.Response:
    found = PLACES.get(request.url.params["name"])
    # When nothing matches, the answer has no "results" at all.
    return httpx.Response(200, json={"results": found} if found else {"generationtime_ms": 0.2})


async def test_openmeteo_search_gives_cities_with_their_geonames_id() -> None:
    om, asked = open_meteo(geocoder)
    assert await om.search("Санкт-Петербург", "ru") == [
        City(
            name="Санкт-Петербург",
            admin="Санкт-Петербург",
            country="Россия",
            lat=59.93863,
            lon=30.31413,
            timezone="Europe/Moscow",
            geo_id=498817,
        )
    ]
    [request] = asked
    assert (request.url.host, request.url.path) == ("geocoding-api.open-meteo.com", "/v1/search")
    assert dict(request.url.params) == {"name": "Санкт-Петербург", "count": "5", "language": "ru"}


@pytest.mark.parametrize(
    ("query", "attempts", "found"),
    [
        ("Санкт Петербург", ["Санкт Петербург", "Санкт-Петербург"], ["Санкт-Петербург"]),
        ("Санкт  Петербург", ["Санкт Петербург", "Санкт-Петербург"], ["Санкт-Петербург"]),
        (" Санкт Петербург\n", ["Санкт Петербург", "Санкт-Петербург"], ["Санкт-Петербург"]),
        (
            "Санкт Петербург, Россия",
            ["Санкт Петербург, Россия", "Санкт-Петербург, Россия"],
            ["Санкт-Петербург"],
        ),
        (
            "Санкт Петербург, Xyzland",
            [
                "Санкт Петербург, Xyzland",
                "Санкт-Петербург, Xyzland",
                "Санкт Петербург",
                "Санкт-Петербург",
            ],
            ["Санкт-Петербург"],
        ),
        ("Paris, Xyzland", ["Paris, Xyzland", "Paris"], ["Paris"]),
        ("Paris , Xyzland", ["Paris , Xyzland", "Paris"], ["Paris"]),
        (
            "Нигде Совсем, Xyzland",
            ["Нигде Совсем, Xyzland", "Нигде-Совсем, Xyzland", "Нигде Совсем", "Нигде-Совсем"],
            [],
        ),
        ("Нигде", ["Нигде"], []),
    ],
)
async def test_openmeteo_search_tries_hyphens_and_the_part_before_the_comma(
    query: str, attempts: list[str], found: list[str]
) -> None:
    om, asked = open_meteo(geocoder)
    assert [city.name for city in await om.search(query, "ru")] == found
    assert [request.url.params["name"] for request in asked] == attempts


async def test_openmeteo_search_empty() -> None:
    om = OpenMeteoClient(client(lambda request: httpx.Response(200, json={})))
    assert await om.search("фывапролдж", "ru") == []


async def test_openmeteo_search_leaves_out_places_it_cannot_save() -> None:
    no_zone = {key: value for key, value in SPB.items() if key != "timezone"}
    odd = [
        # Without a zone the server knows, reminders would go off at the wrong time.
        no_zone,
        SPB | {"timezone": "Mars/Olympus"},
        SPB | {"timezone": "Europe"},  # a folder of the database, not a zone
        SPB | {"timezone": None},
        SPB | {"latitude": 95.0},
        SPB | {"longitude": None},
        SPB | {"name": ""},
        "Paris",
    ]

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.params["name"] == "Санкт Петербург":
            return httpx.Response(200, json={"results": odd})
        return httpx.Response(200, json={"results": [*odd, PARIS]})

    om, asked = open_meteo(answer)
    # Nothing that can be saved counts as nothing found: the hyphenated name is tried next.
    assert [city.name for city in await om.search("Санкт Петербург", "ru")] == ["Paris"]
    assert len(asked) == 2


async def test_openmeteo_search_keeps_only_a_real_geonames_id_region_and_country() -> None:
    odd = [
        SPB | {"id": "498817"},
        SPB | {"id": True},
        SPB | {"id": 2**63},
        {key: value for key, value in SPB.items() if key not in ("id", "admin1", "country")},
        SPB | {"admin1": 7, "country": ""},
    ]
    om, _ = open_meteo(lambda request: httpx.Response(200, json={"results": odd}))
    cities = await om.search("Санкт-Петербург", "ru")
    assert [(city.geo_id, city.admin, city.country) for city in cities] == [
        (None, "Санкт-Петербург", "Россия"),
        (None, "Санкт-Петербург", "Россия"),
        (None, "Санкт-Петербург", "Россия"),
        (None, None, None),
        (498817, None, None),
    ]


@pytest.mark.parametrize(
    "failure",
    [
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(429),
        lambda request: httpx.Response(400, json={"error": True, "reason": "bad count"}),
        lambda request: httpx.Response(200, text="not json"),
        lambda request: httpx.Response(200, json=[SPB]),
        lambda request: httpx.Response(200, json={"results": {"name": "Paris"}}),
        refused,
        timed_out,
    ],
    ids=["500", "429", "400", "not json", "a list", "results not a list", "network", "timeout"],
)
async def test_openmeteo_search_failure_stops_the_attempts_and_is_not_kept(
    failure: Callable[[httpx.Request], httpx.Response],
) -> None:
    failures = [failure]

    def answer(request: httpx.Request) -> httpx.Response:
        return failures.pop()(request) if failures else geocoder(request)

    om, asked = open_meteo(answer)
    with pytest.raises(UpstreamUnavailable):
        await om.search("Санкт Петербург", "ru")
    assert len(asked) == 1  # no hyphens after a failure
    assert [city.name for city in await om.search("Санкт Петербург", "ru")] == ["Санкт-Петербург"]


async def test_openmeteo_search_has_a_deadline_for_each_request() -> None:
    async def answer(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.3 if request.url.params["name"] != "Тула" else 10)
        return geocoder(request)

    om, _ = open_meteo(answer, deadline=0.5)
    # Two attempts take longer than the deadline together, but each one is well within it: a
    # busy machine does not make it run out.
    assert [city.name for city in await om.search("Санкт Петербург", "ru")] == ["Санкт-Петербург"]
    with pytest.raises(UpstreamUnavailable):
        await om.search("Тула", "ru")


async def test_openmeteo_search_is_kept_for_an_hour_whatever_the_case() -> None:
    now = [0.0]
    om, asked = open_meteo(geocoder, clock=lambda: now[0])
    await om.search("Санкт Петербург", "ru")
    assert len(asked) == 2
    now[0] = 3599.9
    assert [city.name for city in await om.search("САНКТ  петербург", "ru")] == ["Санкт-Петербург"]
    await om.search("Нигде", "ru")
    await om.search("нигде", "ru")  # nothing found is kept too
    assert len(asked) == 3
    await om.search("Санкт Петербург", "en")  # another language is another search
    assert len(asked) == 5
    now[0] = 3600.0
    await om.search("Санкт Петербург", "ru")
    assert len(asked) == 7


async def test_openmeteo_search_keeps_256_queries_and_drops_the_oldest() -> None:
    om, asked = open_meteo(geocoder)
    for number in range(257):
        await om.search(f"Город{number}", "ru")
    await om.search("Город1", "ru")  # the second one is still kept
    assert len(asked) == 257
    await om.search("Город0", "ru")  # the first one has gone
    assert len(asked) == 258


async def test_openmeteo_search_takes_no_forecast_slot_and_minds_no_pause() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.open-meteo.com":
            return httpx.Response(503)
        return geocoder(request)

    om, _ = open_meteo(answer)
    with pytest.raises(UpstreamUnavailable):
        await om.forecast(55.75, 37.62)  # forecasts are paused now
    async with om._slots, om._slots:  # and both slots are busy
        # A search that waited for a slot would never get one: the test holds both.
        found = await asyncio.wait_for(om.search("Paris", "en"), 1)
        assert [city.name for city in found] == ["Paris"]


async def test_openmeteo_failed_search_opens_no_pause() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(503)
        return forecast_ok(request)

    om, asked = open_meteo(answer)
    with pytest.raises(UpstreamUnavailable):
        await om.search("Paris", "en")
    await om.forecast(55.75, 37.62)
    assert len(asked) == 2


def test_a_city_chosen_in_a_dialog_before_geo_id_still_loads() -> None:
    saved = {
        "name": "Тула",
        "admin": "Тульская область",
        "country": "Россия",
        "lat": 54.19,
        "lon": 37.62,
        "timezone": "Europe/Moscow",
    }
    assert City(**saved).geo_id is None
