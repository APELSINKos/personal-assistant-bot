from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from assistant.core.clients.cbr import CbrClient, Point
from assistant.core.clients.openmeteo import OpenMeteoClient
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


async def test_openmeteo_search_and_forecast_cache() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if "search" in request.url.path:
            assert request.url.params["name"] == "Владивосток"
            result = {
                "name": "Владивосток",
                "admin1": "Приморский край",
                "country": "Россия",
                "latitude": 43.1,
                "longitude": 131.9,
                "timezone": "Asia/Vladivostok",
            }
            return httpx.Response(200, json={"results": [result]})
        return httpx.Response(200, content=json.dumps({"current": {"time": "2026-09-28T10:00"}}))

    om = OpenMeteoClient(client(handler))
    [city] = await om.search("Владивосток", "ru")
    assert (city.name, city.timezone, city.admin) == (
        "Владивосток",
        "Asia/Vladivostok",
        "Приморский край",
    )
    await om.forecast(43.1, 131.9)
    await om.forecast(43.1, 131.9)
    assert seen.count("/v1/forecast") == 1


async def test_openmeteo_search_empty() -> None:
    om = OpenMeteoClient(client(lambda request: httpx.Response(200, json={})))
    assert await om.search("фывапролдж", "ru") == []
