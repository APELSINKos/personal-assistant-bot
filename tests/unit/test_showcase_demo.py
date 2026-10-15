from __future__ import annotations

import json

import pytest
from scripts.showcase import demo


class Page:
    """A tab that tells what keeps it busy, one answer from the list a question, and draws its
    frames at once."""

    def __init__(self, answers: list[str]) -> None:
        self.answers, self.asked = answers, []

    async def evaluate(self, expression: str) -> object:
        if "requestAnimationFrame" in expression:
            self.asked.append("two frames")
            return None
        self.asked.append("busy?")
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


async def test_a_page_busy_again_after_its_two_frames_is_waited_for() -> None:
    # Calm, then busy again in the two frames that were to end the wait: an entrance that
    # starts with the first render, a font a late layout asks for.
    page = Page(["", "an animation is running", "", ""])
    await demo.settle(page)  # type: ignore[arg-type]
    assert page.asked == ["busy?", "two frames", "busy?", "busy?", "two frames", "busy?"]


async def test_a_page_that_never_calms_down_runs_out_of_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(demo, "SETTLE_TIME", 0.2)
    page = Page(["a font is loading"])
    with pytest.raises(demo.NotSettled, match="a font is loading"):
        await demo.settle(page)  # type: ignore[arg-type]
    assert isinstance(demo.NotSettled("x"), TimeoutError)  # a scene plays once more


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


class Story:
    """A page whose demo answers with the given ids of the story's habit and list."""

    def __init__(self, answer: object) -> None:
        self.answer, self.asked = answer, []

    async def evaluate(self, expression: str) -> object:
        self.asked.append(expression)
        return self.answer


async def test_the_story_s_habit_and_list_are_found_by_their_names() -> None:
    page = Story({"habit": 1, "list": 3})
    assert await demo.story(page, "en") == {"habit": 1, "list": 3}  # type: ignore[arg-type]
    assert '("Sport", "Shopping")' in page.asked[0]
    assert "__demoHost" in page.asked[0]  # the demo's own data, through its host page


async def test_a_demo_without_the_story_says_what_it_misses() -> None:
    with pytest.raises(demo.DemoError, match="no habit «Спорт»"):
        await demo.story(Story({"habit": None, "list": 1}), "ru")  # type: ignore[arg-type]
    with pytest.raises(demo.DemoError, match="no pinned list «Shopping»"):
        await demo.story(Story({"habit": 1, "list": None}), "en")  # type: ignore[arg-type]
    with pytest.raises(demo.DemoError, match="host"):
        await demo.story(Story(None), "ru")  # type: ignore[arg-type]


async def test_the_story_s_habit_is_marked_done_on_the_frozen_day() -> None:
    page = Story(200)
    await demo.mark(page, 3)  # type: ignore[arg-type]
    # The request a tap on its toggle makes, through the demo's host: its JSON as text.
    assert '(3, "2026-10-07")' in page.asked[0]
    assert "__demoHost" in page.asked[0] and 'method: "PUT"' in page.asked[0]
    assert "JSON.stringify({ done: true })" in page.asked[0]
    with pytest.raises(demo.DemoError, match="habit 3 done on 2026-10-07: 422"):
        await demo.mark(Story(422), 3)  # type: ignore[arg-type]
    with pytest.raises(demo.DemoError, match="host"):
        await demo.mark(Story(None), 3)  # type: ignore[arg-type]


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
