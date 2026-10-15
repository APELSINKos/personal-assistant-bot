from __future__ import annotations

import io

import pytest
from PIL import Image
from scripts.showcase import compose, demo, screens


def png(size: tuple[int, int] = (780, 1688)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "#0a0913").save(out, "PNG")
    return out.getvalue()


class Page:
    def __init__(self, done: list[str], size: tuple[int, int]) -> None:
        self.done, self.size = done, size

    async def screenshot(self, **params: object) -> bytes:
        self.done.append(f"shot {params['format']}")
        return png(self.size)


@pytest.fixture
def done(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What the demo was asked to do, in order."""
    done: list[str] = []

    async def load(page: Page, origin: str, route: str, lang: str, theme: str, *, motion: bool):
        done.append(f"load {origin} {route} {lang} {theme} motion={motion}")

    async def story(page: Page, lang: str) -> dict[str, int]:
        return {"habit": 7, "list": 2}

    async def go(page: Page, route: str) -> None:
        done.append(f"go {route}")

    async def check(page: Page) -> None:
        done.append("check")

    for name, stand_in in (("load", load), ("story", story), ("go", go), ("check", check)):
        monkeypatch.setattr(demo, name, stand_in)
    return done


def test_the_screens_are_the_grid_s_and_the_habit_is_the_story_s() -> None:
    assert tuple(screens.ROUTES) == compose.SCREENS
    assert screens.ROUTES["habit"].format(habit=7, list=2) == "/habits/7"


async def test_each_screen_is_taken_on_its_route_once_it_passes_its_checks(
    done: list[str],
) -> None:
    page = Page(done, (780, 1688))
    shots = await screens.shoot(page, "http://127.0.0.1:1", "en", "light")  # type: ignore[arg-type]
    assert list(shots) == list(compose.SCREENS)
    # Less motion: the app's entrances stay off in a still.
    assert done == [
        "load http://127.0.0.1:1 / en light motion=False",
        "check",
        "shot png",
        "go /weather",
        "check",
        "shot png",
        "go /habits/7",
        "check",
        "shot png",
        "go /money",
        "check",
        "shot png",
    ]


async def test_a_shot_not_of_the_whole_device_is_refused(done: list[str]) -> None:
    page = Page(done, (780, 1600))
    with pytest.raises(demo.ShotError, match="today: a picture of 780×1600"):
        await screens.shoot(page, "http://127.0.0.1:1", "ru", "dark")  # type: ignore[arg-type]


def test_a_screen_is_kept_as_webp_of_quality_90() -> None:
    data = screens.encode(png(), "screens/today.dark.webp")
    assert data == compose.webp(Image.open(io.BytesIO(png())).convert("RGB"), 90, 6)
    with Image.open(io.BytesIO(data)) as kept:
        assert (kept.format, kept.size) == ("WEBP", (780, 1688))
