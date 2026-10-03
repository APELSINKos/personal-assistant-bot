from __future__ import annotations

from pathlib import Path

from assistant.core.habit_style import emoji_file
from assistant.core.money_style import (
    CATEGORY_EMOJI,
    CURRENCIES,
    DEFAULT_CURRENCY,
    EXPENSE,
    INCOME,
    OTHER,
    PRESETS,
)

EMOJI_DIR = Path(__file__).resolve().parents[2] / "src" / "assistant" / "assets" / "emoji"


def test_sixteen_currencies_by_their_iso_codes() -> None:
    assert len(CURRENCIES) == 16
    assert next(iter(CURRENCIES)) == DEFAULT_CURRENCY == "RUB"
    assert all(len(code) == 3 and code.isupper() for code in CURRENCIES)
    assert [code for code, currency in CURRENCIES.items() if currency.before] == [
        "USD", "EUR", "GBP",
    ]  # fmt: skip


def test_presets_twelve_expenses_and_four_incomes_with_an_other_of_each_kind() -> None:
    kinds = [preset.kind for preset in PRESETS]
    assert (kinds.count(EXPENSE), kinds.count(INCOME)) == (12, 4)
    keys = [preset.key for preset in PRESETS]
    assert len(set(keys)) == len(keys)
    assert all(len(key) <= 16 for key in keys)  # money_categories.preset
    by_key = {preset.key: preset for preset in PRESETS}
    assert by_key[OTHER[EXPENSE]].kind == EXPENSE
    assert by_key[OTHER[INCOME]].kind == INCOME


def test_the_category_emoji_are_40_distinct_single_characters_each_with_a_picture() -> None:
    assert len(CATEGORY_EMOJI) == len(set(CATEGORY_EMOJI)) == 40
    assert all(len(emoji) == 1 for emoji in CATEGORY_EMOJI)  # no FE0F, no ZWJ
    for emoji in CATEGORY_EMOJI:
        assert (EMOJI_DIR / emoji_file(emoji)).is_file(), emoji


def test_every_preset_emoji_is_in_the_set() -> None:
    assert {preset.emoji for preset in PRESETS} <= set(CATEGORY_EMOJI)
