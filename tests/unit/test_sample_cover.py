from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image
from scripts.cover import draw, favicon, icon

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"
ICONS = ROOT / "webapp" / "demo" / "public"
COVERS = (("ru", "cover.jpg"), ("en", "cover.en.jpg"))


def test_the_covers_fit_a_link_preview() -> None:
    for _, name in COVERS:
        data = (IMAGES / name).read_bytes()
        assert len(data) < 1_000_000, name  # GitHub's limit for a social preview
        with Image.open(io.BytesIO(data)) as cover:
            assert (cover.format, cover.mode, cover.size) == ("JPEG", "RGB", (1280, 640)), name


def test_the_covers_are_what_the_script_draws() -> None:
    # A change to the cover, to the bot's pictures it shows (docs/images) or to the fonts lands
    # here: redraw both with scripts/cover.py; the repository's social preview is then uploaded
    # again by hand.
    for lang, name in COVERS:
        drawn = hashlib.sha256(draw(lang)).hexdigest()
        assert drawn == hashlib.sha256((IMAGES / name).read_bytes()).hexdigest(), name


def test_the_demo_icon_is_what_the_script_draws() -> None:
    # Pixels, not bytes: the PNG's compressed stream differs between the zlib builds of Pillow's
    # wheels (zlib-ng on Windows, zlib on Linux), its pixels do not.
    with (
        Image.open(ICONS / "apple-touch-icon.png") as committed,
        Image.open(io.BytesIO(icon())) as drawn,
    ):
        # Opaque: iOS fills a transparent icon with black.
        assert (committed.format, committed.mode, committed.size) == ("PNG", "RGB", (180, 180))
        assert (drawn.mode, drawn.size) == (committed.mode, committed.size)
        assert drawn.tobytes() == committed.tobytes()


def test_the_demo_tab_shows_the_same_sign() -> None:
    assert (ICONS / "favicon.svg").read_text(encoding="utf-8") == favicon()
