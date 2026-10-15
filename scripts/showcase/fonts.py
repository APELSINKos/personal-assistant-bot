"""The two fonts of the README's pictures from the browser (spec §13.7): Roboto for the text of
the chat pictures, as Telegram on Android draws it, and Noto's colour emoji for every emoji in
the app's screens, the animation and the chats, as the bot's own pictures draw them.

They are fetched once over HTTPS at pinned commits into the user's cache, checked against their
SHA-256 on every use and never committed; both are under the SIL Open Font License. Their cmap
tables tell which characters they draw: a character neither has comes from the machine's own
fonts, so the generator lists such characters (§13.6). The tables are read with the standard
library alone, and nothing here needs a browser.
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen


@dataclass(frozen=True)
class Font:
    file: str  # its name in the cache
    url: str  # at a pinned commit
    size: int
    sha256: str


TEXT = Font(
    "Roboto[wdth,wght].ttf",
    "https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb"
    "/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf",
    488_584,
    "d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134",
)
EMOJI = Font(
    "Noto-COLRv1.ttf",
    "https://raw.githubusercontent.com/googlefonts/noto-emoji"
    "/e20cbc2bbec1926686be9f9bee7d1d2cfa1fea0e/2D/fonts/Noto-COLRv1.ttf",
    5_038_236,
    "b8e25ea68db82f9e4d0aee921f4420be2be39887bd5c893a2ad98710531f9d0c",
)
FONTS = (TEXT, EMOJI)

# What draws nothing of its own: a line break, the emoji presentation selector and the joiner
# between the parts of one emoji.
SILENT = frozenset("\n\ufe0f\u200d")


class FontError(RuntimeError):
    pass


def cache() -> Path:
    """The user's cache folder for the fonts: %LOCALAPPDATA% on Windows, ~/.cache elsewhere."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "personal-assistant-bot" / "showcase"


def download(url: str) -> bytes:
    with urlopen(url, timeout=60) as answer:
        data: bytes = answer.read()
    return data


def _pinned(font: Font, data: bytes) -> bool:
    return len(data) == font.size and hashlib.sha256(data).hexdigest() == font.sha256


def fetch(font: Font, folder: Path | None = None) -> Path:
    """The font's file in the cache, downloaded when it is missing or not the pinned file."""
    folder = cache() if folder is None else folder
    path = folder / font.file
    if path.is_file() and _pinned(font, path.read_bytes()):
        return path
    print(f"Downloading {font.file}")
    data = download(font.url)
    if not _pinned(font, data):
        raise FontError(
            f"{font.file}: {len(data)} bytes with SHA-256 {hashlib.sha256(data).hexdigest()}, "
            f"not the pinned {font.size} bytes with {font.sha256}"
        )
    folder.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_bytes(data)
    part.replace(path)
    return path


def _u16(data: bytes, at: int) -> int:
    value: int = struct.unpack_from(">H", data, at)[0]
    return value


def _u32(data: bytes, at: int) -> int:
    value: int = struct.unpack_from(">I", data, at)[0]
    return value


def _format4(data: bytes, at: int) -> set[int]:
    """Segments of the basic plane: a code maps to code + delta, or through the glyph array."""
    count = _u16(data, at + 6) // 2
    ends = at + 14
    starts = ends + 2 * count + 2  # past the padding word
    deltas = starts + 2 * count
    offsets = deltas + 2 * count
    codes = set()
    for index in range(count):
        start, end = _u16(data, starts + 2 * index), _u16(data, ends + 2 * index)
        delta, offset = _u16(data, deltas + 2 * index), _u16(data, offsets + 2 * index)
        for code in range(start, min(end, 0xFFFE) + 1):
            if offset == 0:
                glyph = (code + delta) & 0xFFFF
            else:
                glyph = _u16(data, offsets + 2 * index + offset + 2 * (code - start))
                glyph = (glyph + delta) & 0xFFFF if glyph else 0
            if glyph:
                codes.add(code)
    return codes


def _format12(data: bytes, at: int) -> set[int]:
    """Groups of codes that map to consecutive glyphs, past the basic plane too."""
    codes = set()
    for group in range(_u32(data, at + 12)):
        start, end, glyph = struct.unpack_from(">III", data, at + 16 + 12 * group)
        codes.update(range(start + (glyph == 0), end + 1))  # glyph 0 draws nothing
    return codes


def coverage(font: bytes | Path) -> frozenset[int]:
    """The code points the font draws: those its Unicode cmap subtables map to a glyph."""
    data = font.read_bytes() if isinstance(font, Path) else font
    tables = {
        data[at : at + 4]: _u32(data, at + 8) for at in range(12, 12 + 16 * _u16(data, 4), 16)
    }
    cmap = tables.get(b"cmap")
    if cmap is None:
        raise ValueError("the font has no cmap table")
    codes: set[int] = set()
    read = False
    for record in range(_u16(data, cmap + 2)):
        platform, encoding = struct.unpack_from(">HH", data, cmap + 4 + 8 * record)
        if platform != 0 and (platform, encoding) not in ((3, 1), (3, 10)):
            continue  # not Unicode
        at = cmap + _u32(data, cmap + 4 + 8 * record + 4)
        kind = _u16(data, at)
        if kind == 4:
            codes |= _format4(data, at)
        elif kind == 12:
            codes |= _format12(data, at)
        else:
            continue  # format 14 and the others say nothing of their own about a character
        read = True
    if not read:
        raise ValueError("the font has no Unicode cmap subtable in format 4 or 12")
    return frozenset(codes)


def outside(text: str, *fonts: frozenset[int]) -> list[str]:
    """The characters of `text` none of the fonts draws, each once, by code point: the browser
    takes them from the machine's own fonts."""
    return sorted(
        {char for char in text if char not in SILENT and not any(ord(char) in f for f in fonts)}
    )


def describe(char: str) -> str:
    """«U+21BB ↻»."""
    return f"U+{ord(char):04X} {char}"
