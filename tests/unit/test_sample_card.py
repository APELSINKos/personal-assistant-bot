from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image
from scripts.habit_card import draw, sample_detail


async def test_the_readme_habit_has_the_numbers_it_was_made_up_for(tmp_path: Path) -> None:
    detail = await sample_detail("ru", tmp_path)
    stats = detail.stats
    assert stats.habit.created_on == date(2025, 6, 2)
    assert (stats.streak, stats.record, stats.week_done, stats.week_goal) == (42, 58, 5, 7)
    assert 80 <= stats.percent <= 90


async def test_the_readme_card_is_drawn_in_both_languages() -> None:
    for lang in ("ru", "en"):
        assert Image.open(BytesIO(await draw(lang))).size == (1080, 1350)
