from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
HTML_LINK = re.compile(r"(?:href|src)=\"([^\"]+)\"")
DOCS = [
    ROOT / "README.md",
    ROOT / "README.en.md",
    ROOT / "CHANGELOG.md",
    ROOT / "deploy" / "server-setup.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_relative_links_resolve(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    for target in MARKDOWN_LINK.findall(text) + HTML_LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        assert (doc.parent / target.split("#")[0]).exists(), f"broken link: {target}"


def test_v1_code_is_gone() -> None:
    for name in ("bot.py", "loader.py", "database.py", "requirements.txt", "testing", "reports"):
        assert not (ROOT / name).exists(), name


def test_license_and_readmes() -> None:
    assert "Copyright (c) 2026 Aleksandr Kovalev" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "README.en.md" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "README.md" in (ROOT / "README.en.md").read_text(encoding="utf-8")
