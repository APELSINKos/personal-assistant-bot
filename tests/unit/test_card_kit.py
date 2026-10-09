from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from assistant.core.habit_style import emoji_file
from assistant.core.services import card_kit as kit

NAME_WIDTH = 748  # the habit card's name: from beside the emoji to the content's right edge


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (1000, 120), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


@pytest.mark.parametrize(
    ("xy", "text", "family", "size", "weight"),
    [
        ((12, 20), "Спорт ёж Йога", "Manrope", 64, 800),
        ((12.375, 20), "Жүгіру · Өскемен", "Manrope", 48, 800),  # Kazakh letters Manrope has
        ((12, 20), "Morning run, 5 km…", "Manrope", 28, 600),
        ((12, 20), "58 дней", "Unbounded", 44, 600),
    ],
)
def test_without_a_fallback_letter_write_draws_what_draw_text_draws(
    xy: tuple[float, float], text: str, family: str, size: int, weight: int
) -> None:
    expected, draw = canvas()
    draw.text(xy, text, font=kit.font(family, size, weight), fill=kit.TEXT)
    written, draw = canvas()
    kit.write(draw, xy, text, family, size, weight, kit.TEXT)
    assert written.tobytes() == expected.tobytes()


def test_a_fallback_piece_sits_on_the_primary_baseline_after_the_piece_before() -> None:
    manrope, onest = kit.font("Manrope", 48, 800), kit.font(kit.FALLBACK, 48, 800)
    expected, draw = canvas()
    baseline = 20 + manrope.getmetrics()[0]  # Onest's own ascent is 5 px less at this size
    x = 12.0
    for piece, face in (("Кітап о", manrope), ("қ", onest), ("у", manrope)):
        draw.text((x, baseline), piece, font=face, fill=kit.TEXT, anchor="ls")
        x += draw.textlength(piece, font=face)
    written, draw = canvas()
    kit.write(draw, (12, 20), "Кітап оқу", "Manrope", 48, 800, kit.TEXT)
    assert written.tobytes() == expected.tobytes()
    assert kit.length(draw, "Кітап оқу", "Manrope", 48, 800) == x - 12


def test_runs_cut_a_line_where_the_font_changes() -> None:
    assert kit.runs("Спорт", "Manrope") == [("Спорт", "Manrope")]
    assert kit.runs("Кітап оқу", "Manrope") == [
        ("Кітап о", "Manrope"),
        ("қ", "Onest"),
        ("у", "Manrope"),
    ]
    assert kit.runs("Қарағанды", "Manrope") == [
        ("Қ", "Onest"),
        ("ара", "Manrope"),
        ("ғ", "Onest"),
        ("анды", "Manrope"),
    ]
    # A space stays in the piece before it; what neither font has is left out, never a box.
    assert kit.runs("Оқ 💪у 读", "Manrope") == [
        ("О", "Manrope"),
        ("қ ", "Onest"),
        ("у ", "Manrope"),
    ]
    assert kit.runs("", "Manrope") == []


def test_drawable_keeps_the_letters_either_font_has() -> None:
    assert kit.drawable("Қарағанды") == "Қарағанды"  # «араанды» before 2.7
    assert kit.drawable("💪 Кітап оқу 读书") == "Кітап оқу"  # an emoji and Chinese still go
    # Every space becomes a plain one, the thin U+2009 that Manrope lacks among them.
    assert kit.drawable("Ақтөбе\u2009—\u00a0Астана") == "Ақтөбе — Астана"
    assert kit.has("Ж", "Manrope") and not kit.has("Қ", "Manrope") and kit.has("Қ", kit.FALLBACK)
    assert not kit.has("读", kit.FALLBACK) and not kit.has(kit.MISSING, kit.FALLBACK)


def test_a_title_takes_the_largest_size_at_which_it_fits_two_lines() -> None:
    _, draw = canvas()
    assert kit.title_lines(draw, "Кітап оқу", NAME_WIDTH) == (64, ["Кітап оқу"])
    size, lines = kit.title_lines(draw, "Ұ" * 50, NAME_WIDTH)
    assert size == 48 and len(lines) == 2 and lines[1].endswith("…")
    for line in lines:  # measured by the pixels drawn, not by `length`
        image, draw = canvas()
        kit.write(draw, (0, 0), line, "Manrope", size, 800, kit.TEXT)
        box = image.getbbox()
        assert box is not None and box[2] <= NAME_WIDTH


def test_emoji_files_leave_out_the_variation_selector() -> None:
    # The weather writes ☀ and ☁ with U+FE0F; noto-emoji names their files without it.
    assert emoji_file("☀\ufe0f") == "emoji_u2600.png"
    assert emoji_file("☁\ufe0f") == "emoji_u2601.png"
    assert emoji_file("💪") == "emoji_u1f4aa.png"
