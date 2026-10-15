from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image
from scripts import cover
from scripts.cover import default_variant, draw, favicon, icon, main

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"
ICONS = ROOT / "webapp" / "demo" / "public"
COVERS = (("ru", "cover.jpg"), ("en", "cover.en.jpg"))


def test_the_covers_fit_a_link_preview() -> None:
    for _, name in COVERS:
        data = (IMAGES / name).read_bytes()
        assert len(data) < 1_000_000, name  # GitHub's limit for a social preview
        with Image.open(io.BytesIO(data)) as picture:
            found = (picture.format, picture.mode, picture.size)
            assert found == ("JPEG", "RGB", (1280, 640)), name


def test_the_covers_are_what_the_script_draws() -> None:
    # A change to the cover, to the demo's dark screens it shows (docs/images/screens), to the
    # phone's frame (scripts/showcase/compose.py) or to the fonts lands here: redraw both with
    # scripts/cover.py; the repository's social preview is then uploaded again by hand.
    for lang, name in COVERS:
        drawn = hashlib.sha256(draw(lang)).hexdigest()
        assert drawn == hashlib.sha256((IMAGES / name).read_bytes()).hexdigest(), name


def test_the_cover_shows_the_demo_once_its_dark_screens_are_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (default_variant("ru"), default_variant("en")) == ("a", "a")
    monkeypatch.setattr(cover, "IMAGES", tmp_path)
    assert (default_variant("ru"), default_variant("en")) == ("b", "b")
    (tmp_path / "screens").mkdir()
    (tmp_path / "screens" / "today.dark.webp").touch()
    assert default_variant("ru") == "b"  # each phone needs its screen
    (tmp_path / "screens" / "weather.dark.webp").touch()
    assert (default_variant("ru"), default_variant("en")) == ("a", "b")


def test_variant_a_is_drawn_on_request(tmp_path: Path) -> None:
    out = tmp_path / "cover.jpg"
    assert main(["--lang", "en", "--variant", "a", "--out", str(out)]) == 0
    assert out.read_bytes() == (IMAGES / "cover.en.jpg").read_bytes()


def test_variant_a_says_which_screen_it_lacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cover, "IMAGES", tmp_path)
    out = tmp_path / "cover.jpg"
    with pytest.raises(SystemExit) as stop:
        main(["--variant", "a", "--out", str(out)])
    assert stop.value.code == 2
    assert "screens/weather.dark.webp" in capsys.readouterr().err
    assert not out.exists()


def test_variant_b_stays_the_fallback() -> None:
    # The bot's pictures fanned out: what the cover shows while the demo's screens are not drawn.
    data = draw("ru", "b")
    assert len(data) < 1_000_000
    assert data != (IMAGES / "cover.jpg").read_bytes()
    with Image.open(io.BytesIO(data)) as fan:
        assert (fan.format, fan.mode, fan.size) == ("JPEG", "RGB", (1280, 640))


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
