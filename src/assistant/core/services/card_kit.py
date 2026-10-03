"""The drawing kit of the share pictures (the habit card, the month report, the rates): one size,
the dark «Вечерний» backdrop and glass, the bundled fonts and emoji, and one drawing thread.

Everything is drawn from assistant/assets only (see SOURCES.md), with Pillow's BASIC layout, so the
same input gives the same bytes on any machine.
"""

from __future__ import annotations

import asyncio
import io
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from assistant.core.habit_style import emoji_file
from assistant.core.i18n import Translator, format_day
from assistant.core.ratelimit import RateLimiter

ASSETS = Path(__file__).resolve().parents[2] / "assets"
WIDTH, HEIGHT = 1080, 1350
PANEL = (48, 48, WIDTH - 48, HEIGHT - 48)
LEFT, RIGHT = 96, WIDTH - 96  # the content's edges inside the panel
BACKGROUND = (10, 9, 19)
GLOWS = ((59, 31, 110), (15, 74, 82))
TEXT = (244, 242, 255)
HINT = (163, 159, 192)
GLASS = (255, 255, 255, 16)
GLASS_LINE = (255, 255, 255, 30)
MISSING = "\ue000"  # a private-use character: no font has it, so it shows the «missing» glyph
QUALITY = 90
CARDS_PER_MINUTE = 6

# One picture at a time per process: each is a tenth of a second of CPU.
DRAWER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="card")


@lru_cache(maxsize=128)
def font(name: str, size: int, weight: int) -> ImageFont.FreeTypeFont:
    # BASIC everywhere: RAQM (Linux, with libfribidi) lays text out differently.
    face = ImageFont.truetype(
        str(ASSETS / "fonts" / f"{name}.ttf"),
        size,
        layout_engine=ImageFont.Layout.BASIC,
    )
    face.set_variation_by_axes([weight])
    return face


@lru_cache(maxsize=1)
def backdrop() -> Image.Image:
    layer = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(layer)
    draw.ellipse((-420, -420, 700, 520), fill=GLOWS[0])
    draw.ellipse((620, 380, 1500, 1100), fill=GLOWS[1])
    return layer.filter(ImageFilter.GaussianBlur(220)).convert("RGBA")


@lru_cache(maxsize=64)
def emoji_image(emoji: str, size: int) -> Image.Image:
    picture = Image.open(ASSETS / "emoji" / emoji_file(emoji)).convert("RGBA")
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def rgb(hex_colour: str) -> tuple[int, int, int]:
    return (int(hex_colour[1:3], 16), int(hex_colour[3:5], 16), int(hex_colour[5:7], 16))


def fit(
    draw: ImageDraw.ImageDraw, text: str, name: str, weight: int, sizes: range, width: float
) -> ImageFont.FreeTypeFont:
    """The largest size of `sizes` (largest first) at which `text` fits in `width`."""
    for size in sizes:
        face = font(name, size, weight)
        if draw.textlength(text, font=face) <= width:
            return face
    return font(name, sizes[-1], weight)


def wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: float, lines: int
) -> list[str] | None:
    """Break `text` into at most `lines` lines of `width` — between words when it can, inside
    a word when it must. None when it does not fit."""
    result: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if draw.textlength(candidate, font=font) <= width:
            line = candidate
            continue
        if line:
            result.append(line)
            line = ""
        while draw.textlength(word, font=font) > width:  # a word longer than a line
            cut = len(word)
            while cut > 1 and draw.textlength(word[:cut], font=font) > width:
                cut -= 1
            result.append(word[:cut])
            word = word[cut:]
        line = word
    if line:
        result.append(line)
    return result if len(result) <= lines else None


def shorten(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: float
) -> str:
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1].rstrip()
    return text + "…"


@lru_cache(maxsize=1024)
def glyph(char: str) -> bytes:
    """`char` as the name font draws it, in raw pixels."""
    face = font("Manrope", 48, 800)
    box = [round(edge) for edge in face.getbbox(char)]
    image = Image.new("L", (max(box[2], 1), max(box[3], 1)))
    ImageDraw.Draw(image).text((0, 0), char, font=face, fill=255)
    return image.tobytes()


def drawable(text: str) -> str:
    """`text` without the characters the name font lacks: an emoji or another script would come
    out as boxes, and the habit's own emoji stands beside the name anyway."""
    composed = unicodedata.normalize("NFC", text)  # a decomposed «й» would lose its breve
    kept = "".join(char for char in composed if char.isspace() or glyph(char) != glyph(MISSING))
    return " ".join(kept.split())


def glass(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int) -> None:
    draw.rounded_rectangle(box, radius, fill=GLASS, outline=GLASS_LINE, width=2)


def card_limiter(clock: Callable[[], float] = monotonic) -> RateLimiter:
    """The budget of CARDS_PER_MINUTE cards a user may have drawn per minute. A process keeps
    one and checks it before drawing: each card is a tenth of a second of CPU."""
    return RateLimiter(CARDS_PER_MINUTE, 60.0, clock)


def footer(draw: ImageDraw.ImageDraw, bot: str, today: date, t: Translator) -> None:
    """The bot, what it is, the day."""
    top = HEIGHT - 48 - 80
    draw.text((LEFT, top), f"@{bot}", font=font("Manrope", 30, 700), fill=TEXT)
    small = font("Manrope", 26, 500)
    draw.text((LEFT, top + 40), t("card-tagline"), font=small, fill=HINT)
    stamp = format_day(today, t.lang, year=True)
    stamp_font = font("Manrope", 26, 600)
    draw.text(
        (RIGHT - draw.textlength(stamp, font=stamp_font), top + 40),
        stamp,
        font=stamp_font,
        fill=HINT,
    )


def jpeg(picture: Image.Image, overlay: Image.Image) -> bytes:
    picture.alpha_composite(overlay)
    out = io.BytesIO()
    picture.convert("RGB").save(out, "JPEG", quality=QUALITY, optimize=True)
    return out.getvalue()


async def draw_in_thread(render: Callable[..., bytes], *args: Any) -> bytes:
    """Draw in the picture thread, off the event loop."""
    return await asyncio.get_running_loop().run_in_executor(DRAWER, render, *args)
