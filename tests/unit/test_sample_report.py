from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.money_report import draw, sample_month

IMAGES = Path(__file__).resolve().parents[2] / "docs" / "images"


async def test_the_readme_month_has_the_numbers_it_was_made_up_for(tmp_path: Path) -> None:
    month, names = await sample_month("ru", tmp_path)
    # The README's alt text says so: 23 600 of 30 000, 6 400 left, 800 a day.
    assert (month.spent, month.budget, month.left, month.per_day) == (
        2_360_000, 3_000_000, 640_000, 80_000,
    )  # fmt: skip
    assert (month.income, month.count) == (550_000, 32)
    assert [names[item.category.id] for item in month.expenses[:5]] == [
        "Продукты", "Кафе", "Развлечения", "Транспорт", "Здоровье",
    ]  # fmt: skip


async def test_the_readme_reports_are_what_the_script_draws() -> None:
    # A change to the report, its fonts or the money rules lands here: redraw (docs/DEVELOPMENT.md).
    for lang, name in (("ru", "money-report.jpg"), ("en", "money-report.en.jpg")):
        drawn = hashlib.sha256(await draw(lang)).hexdigest()
        assert drawn == hashlib.sha256((IMAGES / name).read_bytes()).hexdigest(), name
