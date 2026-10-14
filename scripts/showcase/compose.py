"""The phone around the demo's screens, the grids of four phones and the walk-through's encoding
(spec §13.4, §13.5). Pillow alone: CI makes the grids again from the committed screens without a
browser.

`phone()` is a plain phone of no brand: a body of 54 CSS px radius, 12 px of bezel and a 2 px edge
in the theme's tone, a camera's drop over the status bar and the screen rounded at 44 px, as the
demo's own phone frame draws it (host.css). A shot keeps the demo's status bar and the strip at
the bottom of its screen, so the rounded corners cut neither the clock nor the tabs. The frame is
drawn once for each size of screen, its curves smoothed by drawing them four times larger and
shrinking them, and the same screen always gives the same bytes. It is the one frame of the
grids, the walk-through and the cover's phones (§14): a change to it is a reason to redraw them
all.

`grid()` puts four phones in a row on a transparent page — the dark ones for GitHub's dark theme,
the light ones for its light theme — with a soft shadow of the theme. The budgets are those of
§13.8, which tests/test_repository.py holds the committed files to.
"""

from __future__ import annotations

import functools
import io
from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFilter

SCREENS = ("today", "weather", "habit", "money")  # the grid's order, left to right
WIDTH = 390  # the demo device's CSS px: a shot is 780 px wide at DPR 2
BODY_RADIUS, BEZEL, EDGE, SCREEN_RADIUS = 54, 12, 2, 44  # CSS px, as the demo's phone frame
CAMERA_TOP, CAMERA_SIZE = 10, 14  # the camera's drop, from the screen's top
SUPERSAMPLE = 4
# The body and the edge of the phone (host.css: --phone-body, --phone-edge).
PHONE = {
    "dark": ((0x18, 0x17, 0x20), (0x3A, 0x38, 0x48)),
    "light": ((0xE2, 0xE0, 0xE8), (0xC4, 0xC0, 0xCE)),
}
CAMERA = (0, 0, 0)

GRID_WIDTH = 1760  # shown at 880 in the README
GAP = 40
MARGIN = 64  # around the phones, for their shadow
# The shadow under the phones: its colour, how strong it is, its blur and how far down it falls.
# Black on GitHub's light page, a faint glow of the app's mint on its dark one.
SHADOW = {
    "dark": ((0x7C, 0xF5, 0xC4), 0.22, 26, 0),
    "light": ((0, 0, 0), 0.26, 20, 12),
}

WALK_WIDTH = 540  # shown at 360 in the README
WALK_QUALITY, WALK_COARSER, WALK_METHOD = 80, 72, 4
STILL_QUALITY = 85
# §13.8: a screen, a grid, a still or a chat picture, and the walk-through.
PICTURE_BUDGET = 400_000
ANIMATION_BUDGET = 1_500_000


class BudgetError(RuntimeError):
    """A picture heavier than the README can carry."""


def suffix(lang: str) -> str:
    return "" if lang == "ru" else ".en"


def screen_file(name: str, theme: str, lang: str) -> str:
    """A screen of the demo in docs/images: «screens/habit.dark.webp», «…dark.en.webp»."""
    return f"screens/{name}.{theme}{suffix(lang)}.webp"


def grid_file(theme: str, lang: str) -> str:
    return f"app.{theme}{suffix(lang)}.webp"


def walk_file(lang: str) -> str:
    return f"walkthrough{suffix(lang)}.webp"


def still_file(lang: str) -> str:
    """The walk-through's first frame, for those who asked for less motion."""
    return f"walkthrough.still{suffix(lang)}.webp"


def _rounded(size: tuple[int, int], box: tuple[float, ...], radius: float) -> Image.Image:
    """A mask of a rounded rectangle with smooth edges: drawn four times larger, then shrunk."""
    big = Image.new("L", (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE), 0)
    corners = tuple(round(value * SUPERSAMPLE) for value in box)
    ImageDraw.Draw(big).rounded_rectangle(
        (corners[0], corners[1], corners[2] - 1, corners[3] - 1),
        round(radius * SUPERSAMPLE),
        fill=255,
    )
    return big.resize(size, Image.Resampling.LANCZOS)


@functools.cache
def frame(size: tuple[int, int]) -> tuple[int, Image.Image, Image.Image, Image.Image, Image.Image]:
    """The phone's parts around a screen of `size`, at its scale: how far the screen sits in,
    and the masks of the whole phone, of its body inside the edge, of the screen and of the
    camera."""
    unit = size[0] / WIDTH
    edge, inset = round(EDGE * unit), round((EDGE + BEZEL) * unit)
    whole = (size[0] + 2 * inset, size[1] + 2 * inset)
    outer = _rounded(whole, (0, 0, *whole), (BODY_RADIUS + EDGE) * unit)
    body = _rounded(whole, (edge, edge, whole[0] - edge, whole[1] - edge), BODY_RADIUS * unit)
    screen = _rounded(size, (0, 0, *size), SCREEN_RADIUS * unit)
    left, top = (whole[0] - CAMERA_SIZE * unit) / 2, inset + CAMERA_TOP * unit
    camera = _rounded(
        whole,
        (left, top, left + CAMERA_SIZE * unit, top + CAMERA_SIZE * unit),
        CAMERA_SIZE * unit / 2,
    )
    return inset, outer, body, screen, camera


def phone(screen: Image.Image, theme: str) -> Image.Image:
    """The screen in a phone, RGBA, transparent around its rounded body."""
    body, edge = PHONE[theme]
    inset, outer, inner, rounded, camera = frame(screen.size)
    out = Image.new("RGBA", outer.size, (*edge, 0))
    out.putalpha(outer)
    out.paste((*body, 255), mask=inner)
    out.paste(screen.convert("RGB"), (inset, inset), rounded)
    out.paste((*CAMERA, 255), mask=camera)
    return out


def shrink(image: Image.Image, width: int) -> Image.Image:
    return image.resize(
        (width, round(image.height * width / image.width)), Image.Resampling.LANCZOS
    )


def grid(screens: Sequence[Image.Image], theme: str) -> Image.Image:
    """The phones of the screens in a row, GRID_WIDTH wide, on a transparent page."""
    width = (GRID_WIDTH - 2 * MARGIN - GAP * (len(screens) - 1)) // len(screens)
    phones = [shrink(phone(screen, theme), width) for screen in screens]
    left = (GRID_WIDTH - width * len(phones) - GAP * (len(phones) - 1)) // 2
    places = [(left + index * (width + GAP), MARGIN) for index in range(len(phones))]
    size = (GRID_WIDTH, max(item.height for item in phones) + 2 * MARGIN)
    colour, strength, blur, fall = SHADOW[theme]
    shade = Image.new("L", size, 0)
    for item, (x, y) in zip(phones, places, strict=True):
        shade.paste(item.getchannel("A"), (x, y + fall))
    shade = shade.filter(ImageFilter.GaussianBlur(blur)).point(lambda a: round(a * strength))
    out = Image.new("RGBA", size, (*colour, 0))
    out.putalpha(shade)
    for item, place in zip(phones, places, strict=True):
        out.alpha_composite(item, place)
    return out


def webp(image: Image.Image, quality: int, method: int = 6) -> bytes:
    out = io.BytesIO()
    image.save(out, "WEBP", quality=quality, method=method)
    return out.getvalue()


def picture(image: Image.Image, name: str, quality: int = 90) -> bytes:
    """A screen, a grid or the still as WebP, within the budget of one picture."""
    data = webp(image, quality)
    if len(data) > PICTURE_BUDGET:
        raise BudgetError(f"{name}: {len(data)} bytes, over {PICTURE_BUDGET}")
    return data


def animated(frames: list[Image.Image], durations: list[int], quality: int) -> bytes:
    out = io.BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        quality=quality,
        method=WALK_METHOD,
    )
    return out.getvalue()


def animation(frames: list[Image.Image], durations: list[int]) -> bytes:
    """The walk-through as an animated WebP that loops: at quality 80, or at 72 when that is
    over its budget; a walk-through over it even then stops the run."""
    for quality in (WALK_QUALITY, WALK_COARSER):
        data = animated(frames, durations, quality)
        if len(data) <= ANIMATION_BUDGET:
            return data
        print(f"The walk-through at quality {quality}: {len(data)} bytes")
    raise BudgetError(f"the walk-through: {len(data)} bytes, over {ANIMATION_BUDGET}")
