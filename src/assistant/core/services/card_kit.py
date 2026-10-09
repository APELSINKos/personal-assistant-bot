"""The drawing kit of the share pictures (the habit card, the month report, the rates, the week's
forecast): one size, the dark «Вечерний» backdrop and glass, the bundled fonts and emoji, and one
drawing thread.

Everything is drawn from assistant/assets only (see SOURCES.md), with Pillow's BASIC layout, so the
same input gives the same bytes on any machine. A line of user text is drawn in pieces: a letter its
font lacks comes from the fallback font, on the same baseline.
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
FOOTER_TOP = HEIGHT - 48 - 80  # where footer() begins
BACKGROUND = (10, 9, 19)
GLOWS = ((59, 31, 110), (15, 74, 82))
TEXT = (244, 242, 255)
HINT = (163, 159, 192)
GLASS = (255, 255, 255, 16)
GLASS_LINE = (255, 255, 255, 30)
MISSING = "\ue000"  # a private-use character: no font has it, so it shows the «missing» glyph
# Draws the letters Manrope lacks: the Kazakh Ә Ғ Қ Ң Ұ, the other Cyrillic letters of the CIS
# countries, ʼ and ʻ.
FALLBACK = "Onest"
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


@lru_cache(maxsize=4096)
def has(char: str, family: str) -> bool:
    """Whether the font `family` draws `char`: its pixels differ from the «missing» glyph's."""
    face = font(family, 48, 700)

    def pixels(text: str) -> bytes:
        box = [round(edge) for edge in face.getbbox(text)]
        image = Image.new("L", (max(box[2], 1), max(box[3], 1)))
        ImageDraw.Draw(image).text((0, 0), text, font=face, fill=255)
        return image.tobytes()

    return pixels(char) != pixels(MISSING)


def runs(text: str, family: str) -> list[tuple[str, str]]:
    """`text` in pieces of one font each: a character goes to `family` when it draws it, else to
    the fallback; one that neither draws is left out, so no box is ever drawn. A space stays in
    the piece before it."""
    pieces: list[tuple[str, str]] = []
    for char in text:
        if char == " " and pieces:
            owner = pieces[-1][1]
        elif has(char, family):
            owner = family
        elif has(char, FALLBACK):
            owner = FALLBACK
        else:
            continue
        if pieces and pieces[-1][1] == owner:
            pieces[-1] = (pieces[-1][0] + char, owner)
        else:
            pieces.append((char, owner))
    return pieces


def length(draw: ImageDraw.ImageDraw, text: str, family: str, size: int, weight: int) -> float:
    """The width of `text` as `write` draws it: the widths of its pieces together."""
    return sum(
        draw.textlength(piece, font=font(owner, size, weight))
        for piece, owner in runs(text, family)
    )


def write(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    family: str,
    size: int,
    weight: int,
    fill: tuple[int, ...],
) -> None:
    """Draw `text` where draw.text puts it, by its top left corner: piece after piece, each in its
    own font of the same size and weight, all on the baseline of `family`. Without a letter of
    the fallback, these are the very pixels of draw.text."""
    x, y = xy
    baseline = y + font(family, size, weight).getmetrics()[0]
    for piece, owner in runs(text, family):
        face = font(owner, size, weight)
        draw.text((x, baseline), piece, font=face, fill=fill, anchor="ls")
        x += draw.textlength(piece, font=face)


def fit(
    draw: ImageDraw.ImageDraw, text: str, name: str, weight: int, sizes: range, width: float
) -> ImageFont.FreeTypeFont:
    """The largest size of `sizes` (largest first) at which `text` fits in `width`."""
    for size in sizes:
        if length(draw, text, name, size, weight) <= width:
            return font(name, size, weight)
    return font(name, sizes[-1], weight)


def wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    family: str,
    size: int,
    weight: int,
    width: float,
    lines: int,
    *,
    whole_words: bool = False,
) -> list[str] | None:
    """Break `text` into at most `lines` lines of `width` — between words when it can, inside
    a word when it must, unless `whole_words`. None when it does not fit."""

    def fits(line: str) -> bool:
        return length(draw, line, family, size, weight) <= width

    result: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if fits(candidate):
            line = candidate
            continue
        if line:
            result.append(line)
            line = ""
        if whole_words and not fits(word):
            return None
        while not fits(word):  # a word longer than a line
            cut = len(word)
            while cut > 1 and not fits(word[:cut]):
                cut -= 1
            result.append(word[:cut])
            word = word[cut:]
        line = word
    if line:
        result.append(line)
    return result if len(result) <= lines else None


def shorten(
    draw: ImageDraw.ImageDraw, text: str, family: str, size: int, weight: int, width: float
) -> str:
    while text and length(draw, text + "…", family, size, weight) > width:
        text = text[:-1].rstrip()
    return text + "…"


def title_lines(draw: ImageDraw.ImageDraw, text: str, width: float) -> tuple[int, list[str]]:
    """A title such as a habit's name, in Manrope 800 at 64, 56 or 48 px: the largest at which it
    fits in two lines of `width` with its words whole, or else with a word cut; when even 48
    needs more, the second line ends in «…». The size and the lines."""
    for whole_words in (True, False):
        for size in (64, 56, 48):
            lines = wrap(draw, text, "Manrope", size, 800, width, 2, whole_words=whole_words)
            if lines is not None:
                return size, lines
    lines = wrap(draw, text, "Manrope", 48, 800, width, 99) or [text]
    return 48, [lines[0], shorten(draw, " ".join(lines[1:]), "Manrope", 48, 800, width)]


def drawable(text: str) -> str:
    """`text` without the characters that neither the name font nor the fallback has: an emoji or
    another script would come out as boxes, and the name's own emoji stands beside it anyway.
    Every space becomes a plain one."""
    composed = unicodedata.normalize("NFC", text)  # a decomposed «й» would lose its breve
    kept = "".join(
        char for char in composed if char.isspace() or has(char, "Manrope") or has(char, FALLBACK)
    )
    return " ".join(kept.split())


def glass(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int) -> None:
    draw.rounded_rectangle(box, radius, fill=GLASS, outline=GLASS_LINE, width=2)


def card_limiter(clock: Callable[[], float] = monotonic) -> RateLimiter:
    """The budget of CARDS_PER_MINUTE cards a user may have drawn per minute. A process keeps
    one and checks it before drawing: each card is a tenth of a second of CPU."""
    return RateLimiter(CARDS_PER_MINUTE, 60.0, clock)


def footer(draw: ImageDraw.ImageDraw, bot: str, today: date, t: Translator) -> None:
    """The bot, what it is, the day."""
    draw.text((LEFT, FOOTER_TOP), f"@{bot}", font=font("Manrope", 30, 700), fill=TEXT)
    small = font("Manrope", 26, 500)
    draw.text((LEFT, FOOTER_TOP + 40), t("card-tagline"), font=small, fill=HINT)
    stamp = format_day(today, t.lang, year=True)
    stamp_font = font("Manrope", 26, 600)
    draw.text(
        (RIGHT - draw.textlength(stamp, font=stamp_font), FOOTER_TOP + 40),
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
