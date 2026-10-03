"""Money: the currencies a user can keep accounts in, the preset categories and their emoji.

The emoji set is closed on purpose, as for habits: the month report draws every category's emoji
from a bundled PNG (assets/emoji).
"""

from __future__ import annotations

from dataclasses import dataclass

EXPENSE = "expense"
INCOME = "income"
KINDS = (EXPENSE, INCOME)
DEFAULT_CURRENCY = "RUB"


@dataclass(frozen=True)
class Currency:
    sign: str
    before: bool = False  # in English the sign goes before the number: «$1,200»


# In the order the settings show them.
CURRENCIES: dict[str, Currency] = {
    "RUB": Currency("₽"),
    "USD": Currency("$", before=True),
    "EUR": Currency("€", before=True),
    "KZT": Currency("₸"),
    "BYN": Currency("Br"),
    "UAH": Currency("₴"),
    "UZS": Currency("сўм"),
    "KGS": Currency("сом"),
    "AMD": Currency("֏"),
    "GEL": Currency("₾"),
    "AZN": Currency("₼"),
    "TJS": Currency("смн"),
    "TRY": Currency("₺"),
    "CNY": Currency("¥"),
    "GBP": Currency("£", before=True),
    "PLN": Currency("zł"),
}


@dataclass(frozen=True)
class Preset:
    key: str  # its name is the translation «money-cat-<key>» until the user renames it
    kind: str
    emoji: str


PRESETS: tuple[Preset, ...] = (
    Preset("groceries", EXPENSE, "🛒"),
    Preset("cafe", EXPENSE, "☕"),
    Preset("transport", EXPENSE, "🚌"),
    Preset("home", EXPENSE, "🏠"),
    Preset("phone", EXPENSE, "📱"),
    Preset("health", EXPENSE, "💊"),
    Preset("clothes", EXPENSE, "👕"),
    Preset("fun", EXPENSE, "🎮"),
    Preset("study", EXPENSE, "📚"),
    Preset("gifts", EXPENSE, "🎁"),
    Preset("subscriptions", EXPENSE, "📺"),
    Preset("other", EXPENSE, "📦"),
    Preset("salary", INCOME, "💼"),
    Preset("stipend", INCOME, "🎓"),
    Preset("gifts_in", INCOME, "🎀"),
    Preset("other_in", INCOME, "💰"),
)
# The fallback of each kind: never hidden, so a guess always has somewhere to go.
OTHER = {EXPENSE: "other", INCOME: "other_in"}

# Food and drink, transport, home and body, fun, money and things.
CATEGORY_EMOJI: tuple[str, ...] = (
    "🛒", "☕", "🍔", "🍕", "🍺", "🚌", "🚕", "🚇",
    "⛽", "🚗", "🚲", "🏠", "💡", "🔧", "📱", "💻",
    "💊", "🏥", "🦷", "💇", "👕", "👟", "👶", "🐕",
    "🎮", "🎬", "🎵", "🎨", "📚", "🎓", "🎁", "🎀",
    "🧸", "📺", "💼", "💰", "🏦", "💳", "🧾", "📦",
)  # fmt: skip
