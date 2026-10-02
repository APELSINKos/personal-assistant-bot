from __future__ import annotations

import re

import pytest

from assistant.core.habit_style import COLORS, DEFAULT_COLOR, DEFAULT_EMOJI, EMOJI, emoji_file

# Each theme's page background, its two glows and a card surface: a colour must keep 3:1 on all.
DARK = ("#0a0913", "#3b1f6e", "#0f4a52", "#16141f")
LIGHT = ("#f7f5f2", "#f3d9ff", "#cdeff0", "#ffffff")


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(colour: str) -> float:
    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_the_emoji_set_is_32_distinct_single_characters() -> None:
    assert len(EMOJI) == 32
    assert len(set(EMOJI)) == 32
    assert all(len(emoji) == 1 for emoji in EMOJI)
    assert DEFAULT_EMOJI in EMOJI


def test_emoji_files_follow_the_noto_names() -> None:
    assert emoji_file("💪") == "emoji_u1f4aa.png"
    assert emoji_file("☕") == "emoji_u2615.png"


def test_the_palette_has_eight_colours_with_their_own_circles() -> None:
    assert len(COLORS) == 8
    assert DEFAULT_COLOR in COLORS
    assert len({colour.circle for colour in COLORS.values()}) == 8
    for colour in COLORS.values():
        assert re.fullmatch(r"#[0-9a-f]{6}", colour.dark)
        assert re.fullmatch(r"#[0-9a-f]{6}", colour.light)


@pytest.mark.parametrize("key", sorted(COLORS))
def test_every_colour_keeps_3_to_1_on_its_theme(key: str) -> None:
    colour = COLORS[key]
    assert min(_contrast(colour.dark, background) for background in DARK) >= 3
    assert min(_contrast(colour.light, background) for background in LIGHT) >= 3
