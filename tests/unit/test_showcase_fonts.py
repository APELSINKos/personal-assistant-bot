from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest
from scripts.showcase import fonts


def sfnt(*subtables: tuple[int, int, bytes]) -> bytes:
    """A font file with nothing but a cmap of these (platform, encoding, subtable) records."""
    offset = 4 + 8 * len(subtables)
    records, bodies = b"", b""
    for platform, encoding, body in subtables:
        records += struct.pack(">HHI", platform, encoding, offset + len(bodies))
        bodies += body
    cmap = struct.pack(">HH", 0, len(subtables)) + records + bodies
    directory = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
    return directory + struct.pack(">4sIII", b"cmap", 0, 12 + 16, len(cmap)) + cmap


def format4(segments: list[tuple[int, int, int, list[int] | None]]) -> bytes:
    """Segments (start, end, delta, glyphs): without glyphs a code maps to code + delta, with
    them to its glyph + delta, where a glyph of 0 maps nothing. The closing 0xFFFF segment is
    added here."""
    rows = [*segments, (0xFFFF, 0xFFFF, 1, None)]
    count = len(rows)
    array: list[int] = []
    offsets = []
    for index, (start, end, _, glyphs) in enumerate(rows):
        if glyphs is None:
            offsets.append(0)
            continue
        assert len(glyphs) == end - start + 1
        # From this segment's idRangeOffset word to its first glyph in the array after them.
        offsets.append(2 * (count - index) + 2 * len(array))
        array += glyphs
    body = struct.pack(f">{count}H", *(end for _, end, _, _ in rows)) + b"\0\0"
    body += struct.pack(f">{count}H", *(start for start, _, _, _ in rows))
    body += struct.pack(f">{count}H", *(delta & 0xFFFF for _, _, delta, _ in rows))
    body += struct.pack(f">{count}H", *offsets) + struct.pack(f">{len(array)}H", *array)
    return struct.pack(">7H", 4, 14 + len(body), 0, 2 * count, 0, 0, 0) + body


def format12(groups: list[tuple[int, int, int]]) -> bytes:
    body = b"".join(struct.pack(">III", *group) for group in groups)
    return struct.pack(">HHIII", 12, 0, 16 + len(body), 0, len(groups)) + body


def test_format_4_maps_by_delta_and_through_its_glyph_array() -> None:
    font = sfnt((3, 1, format4([(0x41, 0x43, -0x40 + 3, None), (0x430, 0x433, 0, [7, 0, 9, 0])])))
    assert fonts.coverage(font) == frozenset({0x41, 0x42, 0x43, 0x430, 0x432})


def test_format_12_reaches_past_the_basic_plane() -> None:
    font = sfnt((3, 10, format12([(0x20, 0x21, 1), (0x1F600, 0x1F602, 40)])))
    assert fonts.coverage(font) == frozenset({0x20, 0x21, 0x1F600, 0x1F601, 0x1F602})


def test_a_group_that_starts_at_glyph_0_does_not_map_its_first_code() -> None:
    assert fonts.coverage(sfnt((0, 4, format12([(0x41, 0x42, 0)])))) == frozenset({0x42})


def test_every_unicode_subtable_counts_and_the_others_do_not() -> None:
    font = sfnt(
        (1, 0, struct.pack(">HHH", 0, 262, 0) + bytes(256)),  # Mac Roman, format 0
        (0, 3, format4([(0x41, 0x41, 1, None)])),
        (3, 10, format12([(0x2713, 0x2713, 5)])),
    )
    assert fonts.coverage(font) == frozenset({0x41, 0x2713})


def test_a_font_without_a_unicode_table_it_reads_is_refused() -> None:
    with pytest.raises(ValueError, match="cmap"):
        fonts.coverage(sfnt((1, 0, struct.pack(">HHH", 0, 262, 0) + bytes(256))))


def test_outside_lists_each_character_neither_font_draws_once() -> None:
    text_font = frozenset(map(ord, "Готово ок"))
    emoji = frozenset({0x2705, 0x1F4AA})
    text = "✅ Готово\n↻ ок ✓ ↻ 💪\ufe0f👨\u200d"
    assert fonts.outside(text, text_font, emoji) == ["↻", "✓", "👨"]
    assert fonts.describe("↻") == "U+21BB ↻"
    assert fonts.describe("👨") == "U+1F468 👨"


def pinned(data: bytes) -> fonts.Font:
    digest = hashlib.sha256(data).hexdigest()
    return fonts.Font("Sample[wght].ttf", "https://example.invalid/Sample.ttf", len(data), digest)


def test_fetch_downloads_once_and_keeps_the_checked_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font, asked = pinned(b"glyphs"), []

    def download(url: str) -> bytes:
        asked.append(url)
        return b"glyphs"

    monkeypatch.setattr(fonts, "download", download)
    path = fonts.fetch(font, tmp_path / "cache")
    assert path == tmp_path / "cache" / "Sample[wght].ttf"
    assert path.read_bytes() == b"glyphs"
    assert fonts.fetch(font, tmp_path / "cache") == path
    assert asked == ["https://example.invalid/Sample.ttf"]  # the second time from the cache


def test_fetch_replaces_a_cached_file_that_is_not_the_pinned_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Sample[wght].ttf").write_bytes(b"glyphz")
    monkeypatch.setattr(fonts, "download", lambda url: b"glyphs")
    assert fonts.fetch(pinned(b"glyphs"), tmp_path).read_bytes() == b"glyphs"


def test_fetch_refuses_a_download_that_is_not_the_pinned_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fonts, "download", lambda url: b"glyphz")
    with pytest.raises(fonts.FontError, match=r"Sample\[wght\]\.ttf"):
        fonts.fetch(pinned(b"glyphs"), tmp_path)
    assert list(tmp_path.iterdir()) == []  # nothing half-checked stays in the cache


def test_the_fonts_are_pinned_to_commits() -> None:
    for font in fonts.FONTS:
        assert font.url.startswith("https://raw.githubusercontent.com/"), font.file
        assert any(len(part) == 40 for part in font.url.split("/")), font.file  # a full commit
        assert len(font.sha256) == 64, font.file
    assert {font.file: font.size for font in fonts.FONTS} == {
        "Roboto[wdth,wght].ttf": 488_584,
        "Noto-COLRv1.ttf": 5_038_236,
    }
