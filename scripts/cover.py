"""Draw the project's cover, 1280×640, and the demo's icon.

Usage:  uv run python scripts/cover.py --lang ru --out docs/images/cover.jpg
        uv run python scripts/cover.py --icon webapp/demo/public/apple-touch-icon.png
        uv run python scripts/cover.py --favicon webapp/demo/public/favicon.svg

The cover opens the README and is the link preview of the repository and of the demo: what the
project is, its name, what it does and three chips on the left; on the right, the bot's own
pictures from docs/images — the week's forecast, a habit card and the month's report — fanned out.
Only fixed words and the made-up data of those pictures. It is drawn like them, with card_kit's
fonts, colours and emoji and the BASIC layout, so the same arguments always give the same file.

The icon is a mint speech bubble on the dark «Вечерний», made of rounded rectangles and circles
only, so the PNG drawn by Pillow and the SVG of the demo's tab are one sign.
"""

from __future__ import annotations

import argparse
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from assistant.core.habit_style import COLORS
from assistant.core.services import card_kit as kit

IMAGES = Path(__file__).resolve().parents[1] / "docs" / "images"
WIDTH, HEIGHT = 1280, 640
LEFT, COLUMN = 72, 500  # the words, clear of the ~29 px a 1.91:1 preview cuts off each side
MINT = kit.rgb(COLORS["mint"].dark)
HINT = kit.rgb("#b8b4d3")  # the app's hint: readable over the brightest glow
CHIP_FILL = (255, 255, 255, 18)
CHIP_LINE = (255, 255, 255, 34)
SHADOW = (0, 0, 0, 150)
BOT = "ikbo63_24_bot"

# The bot's pictures, back to front: (name in docs/images, centre, degrees counterclockwise,
# width). Left to right they follow the chips: the weather, a habit, the money.
FAN = (
    ("forecast-card", (790, 345), 9, 290),
    ("money-report", (1066, 345), -9, 290),
    ("habit-card", (928, 322), 0, 315),
)
CORNER_RADIUS = 48  # a picture's corners, at its own size of 1080×1350

# The demo's icon in a square of 180: a speech bubble with its lower left corner square, and
# three dots in it.
ICON = 180
BUBBLE = (30, 40, 150, 128)
BUBBLE_RADIUS = 36
TAIL = (30, 92, 66, 128)
DOTS = (60, 90, 120)
DOT_Y, DOT_RADIUS = 84, 9
TILE_RADIUS = 40  # the tab's tile; iOS rounds the corners of the PNG itself
SUPERSAMPLE = 4  # Pillow draws shapes with hard edges: 4 times larger, then shrunk


@dataclass(frozen=True)
class Words:
    over: str
    title: tuple[str, str]
    tagline: str
    chips: tuple[tuple[str, str], ...]


WORDS = {
    "ru": Words(
        over="Telegram-бот и Mini App",
        title=("Личный", "помощник"),
        # The no-break space keeps the dash off the start of a line.
        tagline="Погода с советами, напоминания фразой, пары, привычки, заметки и деньги"
        "\u00a0— в чате и в приложении",
        chips=(("🌤", "Погода"), ("🎯", "Привычки"), ("💰", "Деньги")),
    ),
    "en": Words(
        over="Telegram bot and Mini App",
        title=("Personal", "Assistant"),
        tagline="Weather with tips, reminders in plain words, classes, habits, notes and money"
        "\u00a0— in the chat and in the app",
        chips=(("🌤", "Weather"), ("🎯", "Habits"), ("💰", "Money")),
    ),
}


def backdrop() -> Image.Image:
    """card_kit's «Вечерний» at the cover's size, with its own glows: kit.backdrop() stays as it
    is, and so do the bytes of the bot's pictures."""
    layer = Image.new("RGB", (WIDTH, HEIGHT), kit.BACKGROUND)
    draw = ImageDraw.Draw(layer)
    draw.ellipse((-380, -420, 640, 400), fill=kit.GLOWS[0])
    draw.ellipse((700, 160, 1600, 900), fill=kit.GLOWS[1])
    return layer.filter(ImageFilter.GaussianBlur(170)).convert("RGBA")


def lines(
    draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int
) -> list[str]:
    """`text` in lines of `width`, broken at plain spaces only."""
    result: list[str] = []
    line = ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if line and draw.textlength(candidate, font=face) > width:
            result.append(line)
            line = word
        else:
            line = candidate
    return [*result, line]


def chips(
    overlay: Image.Image, draw: ImageDraw.ImageDraw, items: tuple[tuple[str, str], ...], top: int
) -> None:
    """Glass chips in a row, an emoji and a word in each."""
    face = kit.font("Manrope", 22, 700)
    capitals = -face.getbbox("H", anchor="ls")[1]
    baseline = round(top + 23 + capitals / 2)  # the capitals in the middle of the chip
    x = LEFT
    for emoji, label in items:
        width = 14 + 28 + 8 + round(draw.textlength(label, font=face)) + 16
        draw.rounded_rectangle(
            (x, top, x + width, top + 46), 23, fill=CHIP_FILL, outline=CHIP_LINE, width=2
        )
        overlay.alpha_composite(kit.emoji_image(emoji, 28), (x + 14, top + 9))
        draw.text((x + 50, baseline), label, font=face, fill=kit.TEXT, anchor="ls")
        x += width + 10
    assert x - 10 <= LEFT + COLUMN, "the chips fit in the column"


def words(cover: Image.Image, lang: str) -> None:
    """The left column: what it is, the name, what it does, three chips and the bot."""
    text = WORDS[lang]
    overlay = Image.new("RGBA", cover.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.text((LEFT, 84), text.over, font=kit.font("Manrope", 26, 700), fill=MINT)
    title = kit.font("Unbounded", 66, 700)
    for row, line in enumerate(text.title):
        draw.text((LEFT, 134 + 80 * row), line, font=title, fill=kit.TEXT)
    tagline = kit.font("Manrope", 27, 500)
    rows = lines(draw, text.tagline, tagline, COLUMN)
    assert len(rows) <= 3, "the tagline takes three lines at most"
    y = 312
    for line in rows:
        draw.text((LEFT, y), line, font=tagline, fill=HINT)
        y += 38
    chips(overlay, draw, text.chips, y + 30)
    draw.text((LEFT, 568), f"@{BOT}", font=kit.font("Manrope", 24, 700), fill=HINT)
    cover.alpha_composite(overlay)


def turned(name: str, angle: float, width: int) -> Image.Image:
    """One of the bot's pictures with rounded corners, turned by `angle` at its own size (sharper
    than turning it small) and then shrunk to `width`."""
    with Image.open(IMAGES / name) as source:
        picture = source.convert("RGBA")
    mask = Image.new("L", picture.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, picture.width - 1, picture.height - 1), CORNER_RADIUS, fill=255
    )
    picture.putalpha(mask)
    scale = width / picture.width
    picture = picture.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    size = (round(picture.width * scale), round(picture.height * scale))
    return picture.resize(size, Image.Resampling.LANCZOS)


def fanned(cover: Image.Image, lang: str) -> None:
    """The bot's pictures fanned out on the right, each with a soft shadow."""
    suffix = "" if lang == "ru" else ".en"
    for name, (centre_x, centre_y), angle, width in FAN:
        picture = turned(f"{name}{suffix}.jpg", angle, width)
        x, y = centre_x - picture.width // 2, centre_y - picture.height // 2
        shadow = Image.new("RGBA", cover.size, (0, 0, 0, 0))
        shadow.paste(SHADOW, (x + 10, y + 24), picture.getchannel("A"))
        cover.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(26)))
        cover.alpha_composite(picture, (x, y))


def draw(lang: str) -> bytes:
    """The cover in `lang`, a JPEG with full colour (no chroma subsampling)."""
    cover = backdrop()
    fanned(cover, lang)
    words(cover, lang)
    out = io.BytesIO()
    cover.convert("RGB").save(out, "JPEG", quality=kit.QUALITY, optimize=True, subsampling=0)
    return out.getvalue()


def icon() -> bytes:
    """The demo's apple-touch-icon, a 180×180 PNG: the sign on a dark square without
    transparency, which iOS would fill with black."""
    big = Image.new("RGB", (ICON * SUPERSAMPLE, ICON * SUPERSAMPLE), kit.BACKGROUND)
    draw = ImageDraw.Draw(big)

    def box(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
        # An SVG shape from x0 to x1 covers Pillow's pixels x0 to x1 - 1, here at 4 times.
        return (x0 * SUPERSAMPLE, y0 * SUPERSAMPLE, x1 * SUPERSAMPLE - 1, y1 * SUPERSAMPLE - 1)

    draw.rounded_rectangle(box(*BUBBLE), BUBBLE_RADIUS * SUPERSAMPLE, fill=MINT)
    draw.rectangle(box(*TAIL), fill=MINT)
    for x in DOTS:
        dot = box(x - DOT_RADIUS, DOT_Y - DOT_RADIUS, x + DOT_RADIUS, DOT_Y + DOT_RADIUS)
        draw.ellipse(dot, fill=kit.BACKGROUND)
    out = io.BytesIO()
    big.resize((ICON, ICON), Image.Resampling.LANCZOS).save(out, "PNG", optimize=True)
    return out.getvalue()


def hex_colour(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def favicon() -> str:
    """The same sign for the demo's tab, an SVG on a rounded dark tile."""
    mint, dark = hex_colour(MINT), hex_colour(kit.BACKGROUND)
    left, top, right, bottom = BUBBLE
    tail_left, tail_top, tail_right, tail_bottom = TAIL
    dots = "".join(
        f'  <circle cx="{x}" cy="{DOT_Y}" r="{DOT_RADIUS}" fill="{dark}"/>\n' for x in DOTS
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ICON} {ICON}">\n'
        f'  <rect width="{ICON}" height="{ICON}" rx="{TILE_RADIUS}" fill="{dark}"/>\n'
        f'  <rect x="{left}" y="{top}" width="{right - left}" height="{bottom - top}"'
        f' rx="{BUBBLE_RADIUS}" fill="{mint}"/>\n'
        f'  <rect x="{tail_left}" y="{tail_top}" width="{tail_right - tail_left}"'
        f' height="{tail_bottom - tail_top}" fill="{mint}"/>\n'
        f"{dots}"
        "</svg>\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="ru", choices=("ru", "en"))
    parser.add_argument(
        "--variant",
        default="b",
        choices=("a", "b"),
        help="the cover's look: b, the bot's pictures fanned out; "
        "a, phones with the demo's dark screens",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--out", type=Path, help="the cover, a JPEG")
    target.add_argument("--icon", type=Path, help="the demo's apple-touch-icon, a PNG")
    target.add_argument("--favicon", type=Path, help="the demo's tab icon, an SVG")
    args = parser.parse_args(argv)
    if args.variant == "a":
        parser.error("variant a, the phones with the demo's dark screens, is not drawn yet")
    if args.icon:
        path, data = args.icon, icon()
    elif args.favicon:
        path, data = args.favicon, favicon().encode()
    else:
        path, data = args.out, draw(args.lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
