from __future__ import annotations

import json

from scripts.showcase import demo


def test_a_shot_opens_the_demo_s_device_at_the_frozen_moment() -> None:
    assert demo.address("http://127.0.0.1:8123", "/weather", "en", "light") == (
        "http://127.0.0.1:8123/demo/index.html?shot=1&at=2026-10-07T10:30&lang=en&theme=light"
        "#/weather"
    )
    assert (demo.WIDTH, demo.HEIGHT, demo.SCALE) == (390, 844, 2)  # 780×1688


def test_the_emoji_font_joins_the_app_s_two_font_variables() -> None:
    css = demo.emoji_css("/showcase/fonts/Noto-COLRv1.ttf")
    assert (
        '@font-face { font-family: "Showcase Emoji"; src: url("/showcase/fonts/Noto-COLRv1.ttf")'
        in css
    )
    assert '--font-text: "Manrope", "Showcase Emoji", system-ui, sans-serif;' in css
    assert '--font-display: "Unbounded", "Manrope", "Showcase Emoji", system-ui, sans-serif;' in css
    assert json.dumps(css) in demo.emoji_script("/showcase/fonts/Noto-COLRv1.ttf")
    assert demo.EMOJI_URL == "/showcase/fonts/Noto-COLRv1.ttf"


def test_the_walk_through_holds_on_to_today_s_classes_only() -> None:
    assert demo.HOOKS == {
        "tab": ".tab",
        "weather card": "a.card.weather-today",
        "hourly strip": ".strip",
        "habit toggle": "button.toggle",
        "habit link": "a.habit__open",
        "money legend": ".legend__row",
        "item check": "input.item__check",
    }
    assert all("data-" not in selector for selector in demo.HOOKS.values())  # no test ids
