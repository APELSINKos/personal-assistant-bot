from __future__ import annotations

import asyncio
import dataclasses
import io
from pathlib import Path

import pytest
from PIL import Image
from scripts.showcase import compose, demo, walk


def jpeg(folder: Path, name: str, colour: str, *, optimize: bool = False) -> Path:
    """A captured frame of the device, 780×1688, as the browser sends it."""
    out = io.BytesIO()
    Image.new("RGB", (780, 1688), colour).save(out, "JPEG", quality=90, optimize=optimize)
    path = folder / f"{name}.jpg"
    path.write_bytes(out.getvalue())
    return path


def test_each_tick_shows_the_last_frame_taken_at_or_before_it() -> None:
    # Ticks every 1/15 s: 0, 0.067, 0.133, 0.2, 0.267, 0.333; the first frame came a little late.
    assert walk.ticks([0.01, 0.05, 0.12, 0.31], 0.4) == [0, 1, 2, 2, 2, 3]
    # A frame taken just after a tick waits for the next one; one taken on a tick is its own.
    assert walk.ticks([0.0, 0.07, 0.2, 0.25], 0.34) == [0, 0, 1, 2, 3]
    assert len(walk.ticks([0.0], 2.8)) == 42  # 15 a second


def framed(path: Path) -> bytes:
    with Image.open(path) as shot:
        return compose.shrink(compose.phone(shot.convert("RGB"), "dark"), 540).tobytes()


def test_equal_neighbours_become_one_longer_frame_and_the_last_one_rests(tmp_path: Path) -> None:
    red, blue, green = (jpeg(tmp_path, colour, colour) for colour in ("red", "blue", "green"))
    again = jpeg(tmp_path, "red again", "red", optimize=True)
    assert again.read_bytes() != red.read_bytes()  # another capture of the same picture
    first = [walk.Frame(0.0, red), walk.Frame(0.1, again), walk.Frame(0.19, blue)]
    frames, durations = walk.assemble([(first, 0.4), ([walk.Frame(0.0, green)], 0.2)])
    # Red for three ticks (two captures of it), blue for three, green for three and the rest.
    assert durations == [200, 200, 200 + 900]
    assert [frame.size for frame in frames] == [(540, round(1744 * 540 / 836))] * 3
    assert [frame.tobytes() for frame in frames] == [framed(red), framed(blue), framed(green)]
    assert frames[0].getpixel((0, 0))[3] == 0  # the phone's air, as in the grids


def test_durations_add_up_without_drifting() -> None:
    # 1000/15 ms is no whole number: each frame ends at the tick it ends at, rounded once.
    assert walk.durations([1, 1, 1, 7, 5]) == [67, 66, 67, 467, 333 + 900]
    assert sum(walk.durations([1] * 150)) == 10_000 + 900


def test_the_scenes_keep_to_the_storyboard() -> None:
    assert [scene.start for scene in walk.SCENES] == [
        "/",
        "/weather",
        "/habits",
        "/",
        "/notes/{list}",
    ]
    for scene in walk.SCENES:
        assert len(scene.acts) <= 2 and scene.length <= 3, scene.name
        assert all(0 < act.at < scene.length for act in scene.acts), scene.name
    total = sum(scene.length for scene in walk.SCENES) + walk.REST
    assert 11.5 <= total <= 13  # «Приложение за 12 секунд»
    # Every hook of the table is held on to, and none other.
    held = {act.hook for scene in walk.SCENES for act in scene.acts}
    held |= {hook for scene in walk.SCENES for hook in (*scene.before, *scene.after)}
    assert held == set(demo.HOOKS)


def test_an_act_finds_its_target_by_what_the_app_says_in_each_language() -> None:
    mark, tap = walk.SCENES[0].acts
    assert (mark.kind, tap.kind) == ("scroll", "tap")
    assert walk.target(tap, "ru") == ("button.toggle", "Спорт")
    assert walk.target(tap, "en") == ("button.toggle", "Sport")
    money = walk.SCENES[3].acts[0]
    assert walk.target(money, "en") == (".tab", "/money")
    tick = walk.SCENES[4].acts[0]
    assert walk.target(tick, "ru") == ("input.item__check:not(:checked)", "")


class Page:
    """A tab whose acts find nothing."""

    def __init__(self) -> None:
        self.scripts: list[str] = []

    async def evaluate(self, expression: str) -> object:
        self.scripts.append(expression)
        return False


async def test_an_act_that_finds_nothing_names_its_hook() -> None:
    page = Page()
    with pytest.raises(demo.MissingHook, match="habit toggle «Sport»"):
        await walk.act(page, walk.SCENES[0].acts[1], "en")  # type: ignore[arg-type]
    assert page.scripts == ['window.__showcase.tap("button.toggle", "Sport", 0)']


class Tab:
    """A tab whose acts find their targets and whose pictures take a moment, as a browser's do."""

    def __init__(self, done: list[str]) -> None:
        self.done = done

    async def evaluate(self, expression: str) -> object:
        if expression == walk.TOUCH:
            self.done.append("touches")
            return None
        self.done.append(expression.removeprefix("window.__showcase."))
        return True

    async def screenshot(self, **params: object) -> bytes:
        await asyncio.sleep(0.01)
        return b"a frame"


@pytest.fixture
def done(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What the demo was asked to do, in order."""
    done: list[str] = []

    async def load(page: Tab, origin: str, route: str, lang: str, theme: str, *, motion: bool):
        done.append(f"load {route} {lang} {theme} motion={motion}")

    async def story(page: Tab, lang: str) -> dict[str, int]:
        done.append(f"story {lang}")
        return {"habit": 4, "list": 7}

    async def mark(page: Tab, habit: int) -> None:
        done.append(f"mark {habit}")

    async def go(page: Tab, route: str) -> None:
        done.append(f"go {route}")

    async def hook(page: Tab, name: str) -> str:
        done.append(f"hook {name}")
        return demo.HOOKS[name]

    async def check(page: Tab) -> None:
        done.append("check")

    stand_ins = {"load": load, "story": story, "mark": mark, "go": go, "hook": hook, "check": check}
    for name, stand_in in stand_ins.items():
        monkeypatch.setattr(demo, name, stand_in)
    return done


def short(scene: walk.Scene) -> walk.Scene:
    """A scene of the table, played in a tenth of a second."""
    acts = tuple(dataclasses.replace(act, at=0.02 * (n + 1)) for n, act in enumerate(scene.acts))
    return dataclasses.replace(scene, length=0.1, acts=acts)


async def test_each_scene_plays_on_the_demo_as_the_story_left_it(
    done: list[str], tmp_path: Path
) -> None:
    played = {}
    for scene in walk.SCENES:
        done.clear()
        folder = tmp_path / scene.name
        frames = await walk.record(Tab(done), "http://127.0.0.1:1", short(scene), "en", folder)  # type: ignore[arg-type]
        assert frames and all(frame.path.parent == folder for frame in frames), scene.name
        played[scene.name] = list(done)
    # «Sport», ticked in the first scene, is done in those after it that show it; the list is
    # the story's. Each screen passes its checks before the touches and the acts.
    assert played == {
        "today": [
            "load / en dark motion=True",
            "hook weather card",
            "hook habit toggle",
            "hook habit toggle",
            "check",
            "touches",
            'scroll("button.toggle", "Sport", 0)',
            'tap("button.toggle", "Sport", 0)',
        ],
        "weather": [
            "load /weather en dark motion=True",
            "hook hourly strip",
            "check",
            "touches",
            'drag(".strip", "", 300)',
        ],
        "habit": [
            "load / en dark motion=True",
            "story en",
            "mark 4",
            "go /habits",
            "hook habit link",
            "check",
            "touches",
            'tap("a.habit__open", "Sport", 0)',
        ],
        "money": [
            "load /habits en dark motion=True",
            "story en",
            "mark 4",
            "go /",
            "hook tab",
            "check",
            "touches",
            'tap(".tab", "/money", 0)',
            "hook money legend",
        ],
        "list": [
            "load / en dark motion=True",
            "story en",
            "go /notes/7",
            "hook item check",
            "check",
            "touches",
            'tap("input.item__check:not(:checked)", "", 0)',
        ],
    }


def test_the_finger_moves_with_what_it_drags() -> None:
    # One step of both in each frame of the page: the finger's own transition next to the
    # browser's smooth scroll left it 0.2 s behind the strip and the page (measured).
    assert "transition: opacity 0.25s;" in walk.TOUCH  # the finger only fades by itself
    assert "transition: transform" not in walk.TOUCH
    assert '"smooth"' not in walk.TOUCH


def test_the_walk_through_is_shown_at_two_thirds() -> None:
    assert (compose.WALK_WIDTH, compose.WALK_QUALITY, compose.WALK_METHOD) == (540, 80, 4)
    assert walk.FPS == 15
