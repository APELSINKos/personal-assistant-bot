from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"
MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
HTML_LINK = re.compile(r"(?:href|src)=\"([^\"]+)\"")
SRC = re.compile(r"\ssrc=\"([^\"]+)\"")
# A <source>'s pictures: comma-separated, each maybe with a descriptor («2x», «780w»).
SRCSET = re.compile(r"srcset=\"([^\"]+)\"")
IMG = re.compile(r"<img\b[^>]*>")
READMES = [ROOT / "README.md", ROOT / "README.en.md"]
# What the README's pictures may weigh (spec §13.8): a screen, a grid, a still or a chat picture
# 400 KB, an animation 1.5 MB; and all the pictures one README shows, both themes of each, the
# animation and its still, the cover and the avatar, 4 MB together. A visitor takes one of each
# pair, about 2.3 MB.
PICTURE_BUDGET = 400_000
ANIMATION_BUDGET = 1_500_000
README_BUDGET = 4_000_000
ANIMATIONS = ("walkthrough.webp", "walkthrough.en.webp")
DOCS = [
    ROOT / "README.md",
    ROOT / "README.en.md",
    ROOT / "CHANGELOG.md",
    ROOT / "deploy" / "server-setup.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]


def sources(text: str) -> list[str]:
    """The pictures of every srcset, without their descriptors."""
    return [
        source.split()[0]
        for sources in SRCSET.findall(text)
        for source in sources.split(",")
        if source.strip()
    ]


def links(text: str) -> list[str]:
    return MARKDOWN_LINK.findall(text) + HTML_LINK.findall(text) + sources(text)


def pictures(text: str) -> set[str]:
    """The pictures a page shows: each src and srcset, once."""
    return set(SRC.findall(text) + sources(text))


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_relative_links_resolve(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    for target in links(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        assert (doc.parent / target.split("#")[0]).exists(), f"broken link: {target}"


def test_a_srcset_names_its_pictures() -> None:
    text = '<source srcset="docs/a.dark.webp, docs/a@2x.dark.webp 2x"><img src="docs/a.webp">'
    assert links(text) == ["docs/a.webp", "docs/a.dark.webp", "docs/a@2x.dark.webp"]


@pytest.mark.parametrize("readme", READMES, ids=lambda path: path.name)
def test_every_readme_picture_says_what_it_shows(readme: Path) -> None:
    for tag in IMG.findall(readme.read_text(encoding="utf-8")):
        assert re.search(r'\salt="[^"\s][^"]*"', tag), f"no alt text: {tag[:80]}"


def test_a_page_shows_each_picture_once() -> None:
    text = (
        '<picture><source srcset="a.dark.webp"><img src="a.webp" alt="A"></picture>'
        '<a href="b.md"><img src="a.webp" alt="A"></a>'
    )
    assert pictures(text) == {"a.webp", "a.dark.webp"}


def test_each_picture_of_the_generator_keeps_to_its_weight() -> None:
    for path in sorted(IMAGES.rglob("*.webp")):
        limit = ANIMATION_BUDGET if path.name in ANIMATIONS else PICTURE_BUDGET
        size = path.stat().st_size
        assert size <= limit, f"{path.relative_to(ROOT).as_posix()}: {size} bytes, over {limit}"


@pytest.mark.parametrize("readme", READMES, ids=lambda path: path.name)
def test_the_pictures_of_a_readme_weigh_4_mb_together_at_most(readme: Path) -> None:
    shown = {
        (readme.parent / target).resolve()
        for target in pictures(readme.read_text(encoding="utf-8"))
        if not target.startswith(("http://", "https://"))
    }
    total = sum(path.stat().st_size for path in shown)
    assert total <= README_BUDGET, f"{readme.name}: {total} bytes, over {README_BUDGET}"


def test_v1_code_is_gone() -> None:
    for name in ("bot.py", "loader.py", "database.py", "requirements.txt", "testing", "reports"):
        assert not (ROOT / name).exists(), name


def test_license_and_readmes() -> None:
    assert "Copyright (c) 2026 Aleksandr Kovalev" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "README.en.md" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "README.md" in (ROOT / "README.en.md").read_text(encoding="utf-8")
