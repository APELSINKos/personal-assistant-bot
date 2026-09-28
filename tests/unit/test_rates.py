from __future__ import annotations

from datetime import date

import pytest

from assistant.core.clients.cbr import Rate, Rates
from assistant.core.services.rates import convert, parse_amount

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
