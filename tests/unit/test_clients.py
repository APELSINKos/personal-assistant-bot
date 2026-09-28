from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from assistant.core.clients.cbr import CbrClient
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
