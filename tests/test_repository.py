from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
HTML_LINK = re.compile(r"(?:href|src)=\"([^\"]+)\"")
# A <source>'s pictures: comma-separated, each maybe with a descriptor («2x», «780w»).
SRCSET = re.compile(r"srcset=\"([^\"]+)\"")
IMG = re.compile(r"<img\b[^>]*>")
READMES = [ROOT / "README.md", ROOT / "README.en.md"]
DOCS = [
    ROOT / "README.md",
    ROOT / "README.en.md",
    ROOT / "CHANGELOG.md",
    ROOT / "deploy" / "server-setup.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]


def links(text: str) -> list[str]:
    found = MARKDOWN_LINK.findall(text) + HTML_LINK.findall(text)
    for sources in SRCSET.findall(text):
        found += [source.split()[0] for source in sources.split(",") if source.strip()]
    return found


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


def test_v1_code_is_gone() -> None:
    for name in ("bot.py", "loader.py", "database.py", "requirements.txt", "testing", "reports"):
        assert not (ROOT / name).exists(), name


def test_license_and_readmes() -> None:
    assert "Copyright (c) 2026 Aleksandr Kovalev" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "README.en.md" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "README.md" in (ROOT / "README.en.md").read_text(encoding="utf-8")
