from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat
from scripts.showcase import compose

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"
PAIRS = [(theme, lang) for theme in ("dark", "light") for lang in ("ru", "en")]


def screen(colour: str = "#2a74c9") -> Image.Image:
    """A made-up shot of the device: 390×844 CSS px at DPR 2."""
    return Image.new("RGB", (780, 1688), colour)


def mean_difference(made: Image.Image, committed: Image.Image) -> list[float]:
    """The mean difference of each channel, colours premultiplied by their alpha: lossy WebP
    keeps no colour under a pixel of alpha 0."""
    bands = zip(made.convert("RGBa").split(), committed.convert("RGBa").split(), strict=True)
    return [ImageStat.Stat(ImageChops.difference(a, b)).mean[0] for a, b in bands]


@pytest.mark.parametrize(("theme", "lang"), PAIRS)
def test_a_grid_is_what_compose_makes_of_the_committed_screens(theme: str, lang: str) -> None:
    # The four screens in docs/images/screens are the sources of the grid. Encoded as the
    # generator encodes it, WebP q90 with method 6, a grid comes out byte for byte the same with
    # one libwebp; another machine's may differ a little, never by half a step on average. A
    # grid set side by side with its unencoded self would not do: q90 alone moves each channel
    # by about 1 on average.
    with (IMAGES / compose.grid_file(theme, lang)).open("rb") as file:
        committed = Image.open(file)
        committed.load()
    sources = []
    for name in compose.SCREENS:
        with Image.open(IMAGES / compose.screen_file(name, theme, lang)) as shot:
            sources.append(shot.convert("RGB"))
    out = io.BytesIO()
    compose.grid(sources, theme).save(out, "WEBP", quality=90, method=6)
    made = Image.open(out)
    assert (made.mode, made.size) == (committed.mode, committed.size) == ("RGBA", made.size)
    assert made.width == compose.GRID_WIDTH
    difference = mean_difference(made, committed)
    assert max(difference) < 0.5, difference


def test_the_screens_are_the_demo_s_device_at_dpr_2() -> None:
    for theme, lang in PAIRS:
        for name in compose.SCREENS:
            with Image.open(IMAGES / compose.screen_file(name, theme, lang)) as shot:
                assert (shot.format, shot.size) == ("WEBP", (780, 1688)), shot.filename


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_a_phone_is_drawn_the_same_twice(theme: str) -> None:
    first = compose.phone(screen(), theme).tobytes()
    compose.frame.cache_clear()  # the frame drawn anew, not taken from the first call
    assert compose.phone(screen(), theme).tobytes() == first


def test_a_phone_frames_the_screen_with_rounded_corners_and_air_around() -> None:
    shot = screen()
    shot.putpixel((390, 844), (255, 0, 0))
    phone = compose.phone(shot, "dark")
    # 12 CSS px of bezel and 2 of edge on each side, at the shot's two pixels to one.
    assert (phone.mode, phone.size) == ("RGBA", (780 + 56, 1688 + 56))
    assert phone.getpixel((0, 0))[3] == 0  # outside the rounded body
    assert phone.getpixel((28 + 390, 28 + 844)) == (255, 0, 0, 255)  # the screen, as shot
    # The body, where the screen's corner is rounded off.
    assert phone.getpixel((50, 50)) == (*compose.PHONE["dark"][0], 255)
    assert phone.getpixel((418, 1)) == (*compose.PHONE["dark"][1], 255)  # the edge
    assert phone.getpixel((418, 28 + 20 + 14)) == (0, 0, 0, 255)  # the camera, over the status bar
    assert phone.getpixel((418, 28 + 60)) == (42, 116, 201, 255)  # below it, the screen again


def test_a_grid_is_four_phones_in_a_row_on_a_transparent_page() -> None:
    made = compose.grid([screen(colour) for colour in ("red", "green", "blue", "white")], "light")
    assert (made.mode, made.width) == ("RGBA", compose.GRID_WIDTH)
    assert made.getpixel((0, 0))[3] == 0  # GitHub's own page shows through
    middle = made.height // 2
    opaque = {x for x in range(made.width) if made.getpixel((x, middle))[3] == 255}
    starts = sorted(x for x in opaque if x - 1 not in opaque)
    assert len(starts) == 4
    assert {b - a for a, b in zip(starts, starts[1:], strict=False)} == {starts[1] - starts[0]}
    colours = [made.getpixel((x + 60, middle))[:3] for x in starts]
    assert colours == [(255, 0, 0), (0, 128, 0), (0, 0, 255), (255, 255, 255)]


def test_an_animation_loops_and_one_over_its_budget_is_encoded_again_more_coarsely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [Image.new("RGBA", (54, 112), colour) for colour in ("red", "blue")]
    with Image.open(io.BytesIO(compose.animation(frames, [500, 700]))) as made:
        assert (made.format, made.n_frames, made.info["loop"]) == ("WEBP", 2, 0)
        made.seek(1)
        made.load()
        assert made.info["duration"] == 700
    asked: list[int] = []

    def sized(frames: list[Image.Image], durations: list[int], quality: int) -> bytes:
        asked.append(quality)
        return bytes(quality * 10)  # 800 bytes at q80, 720 at q72

    monkeypatch.setattr(compose, "animated", sized)
    monkeypatch.setattr(compose, "ANIMATION_BUDGET", 750)
    assert compose.animation(frames, [500, 500]) == bytes(720)
    assert asked == [80, 72]
    monkeypatch.setattr(compose, "ANIMATION_BUDGET", 700)
    asked.clear()
    with pytest.raises(compose.BudgetError, match="walk-through: 720 bytes, over 700"):
        compose.animation(frames, [500, 500])
    assert asked == [80, 72]


def test_a_picture_over_its_budget_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compose, "PICTURE_BUDGET", 50)
    with pytest.raises(compose.BudgetError, match="app.dark.webp"):
        compose.picture(Image.effect_noise((64, 64), 60), "app.dark.webp")


def test_the_walk_through_loops_in_its_phone_and_its_still_is_its_first_frame() -> None:
    for lang in ("ru", "en"):
        with Image.open(IMAGES / compose.walk_file(lang)) as walk:
            assert (walk.format, walk.width, walk.info["loop"]) == ("WEBP", 540, 0)
            assert walk.n_frames > 1
            durations = []
            for index in range(walk.n_frames):
                walk.seek(index)
                walk.load()
                durations.append(walk.info["duration"])
            assert 11_000 <= sum(durations) <= 13_500, sum(durations)  # «за 12 секунд»
            walk.seek(0)
            first = walk.convert("RGBA")
        with Image.open(IMAGES / compose.still_file(lang)) as still:
            assert (still.format, still.size) == ("WEBP", first.size)
            assert getattr(still, "n_frames", 1) == 1
            assert first.getpixel((0, 0))[3] == still.convert("RGBA").getpixel((0, 0))[3] == 0
            assert max(mean_difference(still.convert("RGBA"), first)) < 3


def test_the_files_are_named_as_the_readme_shows_them() -> None:
    assert compose.SCREENS == ("today", "weather", "habit", "money")  # the grid's order
    assert compose.screen_file("habit", "dark", "ru") == "screens/habit.dark.webp"
    assert compose.screen_file("money", "light", "en") == "screens/money.light.en.webp"
    assert compose.grid_file("dark", "ru") == "app.dark.webp"
    assert compose.grid_file("light", "en") == "app.light.en.webp"
    assert compose.walk_file("ru") == "walkthrough.webp"
    assert compose.walk_file("en") == "walkthrough.en.webp"
    assert compose.still_file("ru") == "walkthrough.still.webp"
    assert compose.still_file("en") == "walkthrough.still.en.webp"
