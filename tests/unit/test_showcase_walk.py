from __future__ import annotations

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


def test_the_walk_through_is_shown_at_two_thirds() -> None:
    assert (compose.WALK_WIDTH, compose.WALK_QUALITY, compose.WALK_METHOD) == (540, 80, 4)
    assert walk.FPS == 15
