from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.showcase import manifest

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"


def test_the_committed_pictures_are_those_the_generator_recorded() -> None:
    # A regeneration left halfway, a picture changed by hand or a transcript edited without
    # redrawing its pictures lands here: run `uv run python -m scripts.showcase` (spec §13.8).
    assert manifest.problems(IMAGES) == []


@pytest.fixture
def images(tmp_path: Path) -> Path:
    """A folder like docs/images after a run: a screen, a chat picture and its transcript."""
    folder = tmp_path / "images"
    (folder / "screens").mkdir(parents=True)
    (folder / "chat").mkdir()
    (folder / "screens" / "today.dark.webp").write_bytes(b"today")
    (folder / "chat" / "week.dark.webp").write_bytes(b"week")
    (folder / "chat" / "chats.json").write_text(json.dumps(TRANSCRIPT), encoding="utf-8")
    (folder / "habit-card.jpg").write_bytes(b"drawn by scripts/habit_card.py")
    return folder


TRANSCRIPT = {
    "morning": {
        "messages": [{"from": "bot", "at": "2026-10-07T08:00", "text": "☀\ufe0f Доброе утро"}]
    },
    "week": {"messages": [{"from": "bot", "at": "2026-10-07T08:00", "text": "📅 Неделя"}]},
}
WRITTEN = ("screens/today.dark.webp", "chat/week.dark.webp", "chat/chats.json")


def recorded(images: Path) -> manifest.Manifest:
    return manifest.record(
        images,
        [images / name for name in WRITTEN],
        commit="8f615d2c" * 5,
        browser="Microsoft Edge 155.0.4283.45",
        scenes={"chat/chats.json": manifest.scene_sums(TRANSCRIPT)},
        from_system_font=["U+21BB ↻"],
    )


def test_a_recorded_run_is_in_step_with_its_files(images: Path) -> None:
    record = recorded(images)
    assert manifest.load(images) == record
    assert record.files["screens/today.dark.webp"] == manifest.File(
        5, hashlib.sha256(b"today").hexdigest()
    )
    assert sorted(record.files) == sorted(WRITTEN)  # the cards of other scripts are not its
    assert manifest.problems(images) == []
    saved = json.loads((images / "showcase.json").read_text(encoding="utf-8"))
    assert saved["browser"] == "Microsoft Edge 155.0.4283.45"
    assert saved["from_system_font"] == ["U+21BB ↻"]
    assert saved["scenes"]["chat/chats.json"]["week"] == manifest.scene_sums(TRANSCRIPT)["week"]


def test_a_scene_sum_is_the_sum_of_its_canonical_json() -> None:
    week = {"messages": [{"text": "📅 Неделя", "from": "bot"}], "menu": None}
    canonical = '{"menu":null,"messages":[{"from":"bot","text":"📅 Неделя"}]}'
    assert manifest.scene_sums({"week": week}) == {
        "week": hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    }


def test_a_picture_changed_after_the_run_is_found(images: Path) -> None:
    recorded(images)
    (images / "screens" / "today.dark.webp").write_bytes(b"redrawn halfway")
    assert manifest.problems(images) == [
        "screens/today.dark.webp: not the file showcase.json records"
    ]


def test_pictures_missing_or_unrecorded_are_found(images: Path) -> None:
    recorded(images)
    (images / "chat" / "week.dark.webp").unlink()
    (images / "app.dark.webp").write_bytes(b"a grid nobody recorded")
    assert manifest.problems(images) == [
        "chat/week.dark.webp: in showcase.json, not on disk",
        "app.dark.webp: on disk, not in showcase.json",
    ]


def test_a_transcript_edited_without_its_pictures_is_found(images: Path) -> None:
    recorded(images)
    edited = {**TRANSCRIPT, "week": {"messages": [{"from": "bot", "text": "📅 Week"}]}}
    (images / "chat" / "chats.json").write_text(json.dumps(edited), encoding="utf-8")
    assert manifest.problems(images) == [
        "chat/chats.json: not the file showcase.json records",
        "chat/chats.json: scene week is not the one its pictures were drawn from",
    ]
    # A run that writes the transcript without drawing its pictures records the file as it is,
    # but not the scene the pictures were drawn from.
    manifest.record(images, [images / "chat" / "chats.json"], commit="0" * 40)
    assert manifest.problems(images) == [
        "chat/chats.json: scene week is not the one its pictures were drawn from"
    ]


def test_a_later_run_keeps_what_it_did_not_draw(images: Path) -> None:
    first = recorded(images)
    (images / "screens" / "today.dark.webp").write_bytes(b"today again")
    later = manifest.record(images, [images / "screens" / "today.dark.webp"], commit="1" * 40)
    assert later.files["chat/week.dark.webp"] == first.files["chat/week.dark.webp"]
    assert later.files["screens/today.dark.webp"].size == len(b"today again")
    assert (later.browser, later.scenes, later.from_system_font) == (
        first.browser,
        first.scenes,
        first.from_system_font,
    )
    assert later.commit == "1" * 40
    # A run that wrote nothing changes nothing, not even the commit.
    assert manifest.record(images, [], commit="2" * 40) == later


def test_a_transcript_needs_the_sums_of_its_scenes(images: Path) -> None:
    manifest.record(images, [images / name for name in WRITTEN], commit="0" * 40)
    assert manifest.problems(images) == ["chat/chats.json: no scene sums in showcase.json"]


def test_only_the_generator_s_files_in_the_images_folder_are_recorded(images: Path) -> None:
    with pytest.raises(ValueError, match="habit-card.jpg"):
        manifest.record(images, [images / "habit-card.jpg"], commit="0" * 40)
    outside = images.parent / "secret.webp"
    outside.write_bytes(b"not a picture of the README")
    with pytest.raises(ValueError, match="outside"):
        manifest.record(images, [outside], commit="0" * 40)
    assert not (images / "showcase.json").exists()


def test_without_a_manifest_nothing_is_in_step(images: Path) -> None:
    assert manifest.problems(images) == ["showcase.json is missing"]


def test_an_empty_manifest_fits_a_folder_without_pictures(tmp_path: Path) -> None:
    (tmp_path / "cover.jpg").write_bytes(b"drawn by scripts/cover.py")
    manifest.record(tmp_path, [], commit="0" * 40)
    assert manifest.load(tmp_path) == manifest.Manifest()
    assert manifest.problems(tmp_path) == []
