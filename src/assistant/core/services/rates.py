"""Amount parsing and conversion between roubles and USD/EUR."""

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
