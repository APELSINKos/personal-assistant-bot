"""Amount parsing and conversion: roubles and USD/EUR for the bot, any currency of the day for
the app."""

from __future__ import annotations

import math

from assistant.core.clients.cbr import Rates
from assistant.core.config import LIMITS


def parse_amount(text: str) -> float | None:
    cleaned = text.replace(" ", "").replace("\N{NO-BREAK SPACE}", "").replace(",", ".")
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(amount) or not 0 < amount <= LIMITS.amount_max:
        return None
    return amount


def convert(amount: float, source: str, target: str, rates: Rates) -> float:
    table = {"USD": rates.usd.value, "EUR": rates.eur.value}
    if source == "RUB" and target in table:
        return amount / table[target]
    if target == "RUB" and source in table:
        return amount * table[source]
    raise ValueError(f"unsupported conversion {source}->{target}")


def cross(amount: float, source: str, target: str, rates: Rates) -> float:
    """Any currency of the day into any other, through the rouble; ValueError for one the bank
    does not quote."""

    def roubles(code: str) -> float:
        if code == "RUB":
            return 1.0
        if code not in rates.currencies:
            raise ValueError(f"unknown currency {code}")
        return rates.currencies[code].value

    return amount * roubles(source) / roubles(target)
