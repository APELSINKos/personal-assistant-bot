from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from scripts.habit_card import draw, sample_detail

IMAGES = Path(__file__).resolve().parents[2] / "docs" / "images"


async def test_the_readme_habit_has_the_numbers_it_was_made_up_for(tmp_path: Path) -> None:
    detail = await sample_detail("ru", tmp_path)
    stats = detail.stats
    assert stats.habit.created_on == date(2025, 6, 2)
    assert (stats.streak, stats.record, stats.week_done, stats.week_goal) == (42, 58, 5, 7)
    assert stats.percent == 85  # the README's alt text says so


async def test_the_readme_cards_are_what_the_script_draws() -> None:
    # A change to the card, its fonts or the habit rules lands here: redraw (docs/DEVELOPMENT.md).
    for lang, name in (("ru", "habit-card.jpg"), ("en", "habit-card.en.jpg")):
        drawn = hashlib.sha256(await draw(lang)).hexdigest()
        assert drawn == hashlib.sha256((IMAGES / name).read_bytes()).hexdigest(), name
