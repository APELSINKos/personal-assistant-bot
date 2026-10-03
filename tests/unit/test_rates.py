from __future__ import annotations

from datetime import date

import pytest

from assistant.core.clients.cbr import Rate, Rates
from assistant.core.services.rates import convert, cross, parse_amount

RATES = Rates(date(2026, 9, 28), Rate(84.2, -0.31), Rate(96.67, -0.83))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("100", 100.0),
        ("99,5", 99.5),
        ("1 500,50", 1500.5),
        ("1000000000", 1e9),
        ("0", None),
        ("-5", None),
        ("nan", None),
        ("inf", None),
        ("1e10", None),
        ("abc", None),
        ("", None),
        ("   ", None),
    ],
)
def test_parse_amount(text: str, expected: float | None) -> None:
    assert parse_amount(text) == expected


def test_convert_both_directions() -> None:
    assert convert(100, "USD", "RUB", RATES) == pytest.approx(8420.0)
    assert convert(9667, "RUB", "EUR", RATES) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        convert(1, "USD", "EUR", RATES)


def test_cross_rates_between_any_currencies_of_the_day() -> None:
    usd, eur, amd = Rate(80.0, 0.0), Rate(100.0, 0.0), Rate(0.2, 0.0)
    rates = Rates(date(2026, 10, 3), usd, eur, {"USD": usd, "EUR": eur, "AMD": amd})
    assert cross(100, "USD", "EUR", rates) == pytest.approx(80.0)
    assert cross(8000, "RUB", "USD", rates) == pytest.approx(100.0)
    assert cross(1000, "AMD", "RUB", rates) == pytest.approx(200.0)
    assert cross(5, "RUB", "RUB", rates) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        cross(1, "GBP", "RUB", rates)
