from __future__ import annotations

import io
import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image
from scripts.showcase import __main__ as showcase
from scripts.showcase import compose, manifest, readme, walk

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def run(tmp_path: Path) -> showcase.Run:
    (tmp_path / "images").mkdir()
    (tmp_path / "work").mkdir()
    return showcase.Run(
        langs=("ru",), themes=("dark",), work=tmp_path / "work", images=tmp_path / "images"
    )


def test_a_run_records_what_its_steps_wrote(run: showcase.Run) -> None:
    done = []

    async def screens(run: showcase.Run) -> None:
        done.append("screens")
        run.write("screens/today.dark.webp", b"today")

    async def chats(run: showcase.Run) -> None:
        done.append("chats")
        run.write("chat/chats.json", b'{"week": {"messages": []}}')
        run.scenes["chat/chats.json"] = manifest.scene_sums({"week": {"messages": []}})
        run.from_system_font = ["U+21BB ↻"]

    showcase.generate((showcase.Step("screens", screens), showcase.Step("chats", chats)), run)
    assert done == ["screens", "chats"]  # in the order of `all`
    recorded = manifest.load(run.images)
    assert sorted(recorded.files) == ["chat/chats.json", "screens/today.dark.webp"]
    assert recorded.commit == showcase.head()
    assert recorded.from_system_font == ["U+21BB ↻"]
    assert manifest.problems(run.images) == []


def test_a_run_that_fails_leaves_the_manifest_as_it_was(run: showcase.Run) -> None:
    async def first(run: showcase.Run) -> None:
        run.write("screens/today.dark.webp", b"today")

    async def broken(run: showcase.Run) -> None:
        run.write("screens/today.dark.webp", b"today, redrawn")
        raise RuntimeError("the browser went away")

    showcase.generate((showcase.Step("screens", first),), run)
    with pytest.raises(RuntimeError):
        showcase.generate((showcase.Step("screens", broken),), run)
    # The regeneration left halfway shows: the picture is not the one the manifest records.
    assert manifest.problems(run.images) == [
        "screens/today.dark.webp: not the file showcase.json records"
    ]


def test_a_step_writes_into_the_images_folder_only(run: showcase.Run) -> None:
    with pytest.raises(ValueError, match="README.md"):
        run.write("../README.md", b"<!-- -->")
    assert not (run.images.parent / "README.md").exists()


def test_a_step_never_overwrites_a_picture_of_another_script(run: showcase.Run) -> None:
    # The cards, the forecast and the cover in docs/images are drawn by scripts of their own:
    # the name is refused before anything is written, not when the manifest is recorded.
    (run.images / "forecast-card.jpg").write_bytes(b"drawn by scripts/forecast_card.py")
    for name in ("forecast-card.jpg", "cover.jpg", "screens/../showcase.json", "chat.webp"):
        with pytest.raises(ValueError, match="not a picture of the generator"):
            run.write(name, b"overwritten")
    assert (run.images / "forecast-card.jpg").read_bytes() == b"drawn by scripts/forecast_card.py"
    assert sorted(path.name for path in run.images.iterdir()) == ["forecast-card.jpg"]
    assert run.written == []


def test_a_run_prepares_only_what_its_steps_need(
    run: showcase.Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared: list[str] = []

    @contextmanager
    def serve(routes: dict[str, Path]) -> Iterator[object]:
        prepared.append("server " + " ".join(sorted(routes)))
        yield object()

    monkeypatch.setattr(showcase, "build_demo", lambda: prepared.append("demo"))
    monkeypatch.setattr(showcase.cdp, "find", lambda given: prepared.append(f"browser {given}"))
    monkeypatch.setattr(showcase.fonts, "fetch", lambda font: prepared.append(font.file))
    monkeypatch.setattr(showcase.serve, "serve", serve)

    async def nothing(run: showcase.Run) -> None:
        pass

    showcase.generate((showcase.Step("compose", nothing),), run)
    assert prepared == []
    showcase.generate((showcase.Step("chats", nothing, browser=True),), run, browser="edge")
    assert prepared == [
        "browser edge",
        "Roboto[wdth,wght].ttf",
        "Noto-COLRv1.ttf",
        "server /demo/ /showcase/ /showcase/fonts/",
    ]
    prepared.clear()
    showcase.generate((showcase.Step("screens", nothing, demo=True, browser=True),), run)
    # A machine without Edge or Chrome stops before the demo's build, npm ci and all.
    assert prepared[:2] == ["browser None", "demo"]


SCENES = {
    name: {"messages": [{"from": "bot", "at": "2026-10-07T08:00", "text": name, "inline": []}]}
    for name in readme.ORDER
}


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (780, 100), "#0e1621").save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def chats_drawn(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The chats step with a made-up transcript and a browser that draws plain shots."""
    shot: list[str] = []

    async def record(lang: str) -> dict[str, object]:
        return SCENES

    async def shoot(run: showcase.Run, pages: dict[str, str]) -> dict[str, bytes]:
        shot.extend(pages.values())
        return {scene: png() for scene in pages}

    monkeypatch.setattr(showcase.chats, "record", record)
    monkeypatch.setattr(showcase, "_shoot_chats", shoot)
    monkeypatch.setattr(showcase, "_from_system_font", lambda images: ["U+21BB ↻"])
    return shot


async def test_the_chats_of_one_theme_leave_the_scenes_unrecorded(
    run: showcase.Run, chats_drawn: list[str]
) -> None:
    # The light pictures may still show an older transcript: only a run of both themes says
    # which transcript the pictures come from.
    await showcase.draw_chats(run)
    assert len(chats_drawn) == 6
    assert (run.images / "chat" / "chats.json").is_file()
    assert (run.images / "chat" / "morning.dark.webp").is_file()
    assert not (run.images / "chat" / "morning.light.webp").exists()
    assert run.scenes == {}
    assert run.from_system_font == ["U+21BB ↻"]
    run.themes = ("dark", "light")
    await showcase.draw_chats(run)
    assert run.scenes == {"chat/chats.json": manifest.scene_sums(SCENES)}


async def test_the_readme_step_writes_between_the_markers_only(
    run: showcase.Run, tmp_path: Path
) -> None:
    (run.images / "chat").mkdir()
    (run.images / "chat" / "chats.json").write_text(json.dumps(SCENES), encoding="utf-8")
    run.readmes = tmp_path
    before, after = "# Личный помощник\n\n", "\n\n## Mini App\n"
    path = tmp_path / "README.md"
    path.write_text(f"{before}{readme.START}{readme.END}{after}", encoding="utf-8")
    await showcase.draw_readme(run)
    text = path.read_text(encoding="utf-8")
    assert text == f"{before}{readme.START}{readme.render(SCENES, 'ru')}{readme.END}{after}"
    assert not (tmp_path / "README.en.md").exists()  # --lang ru


def test_all_runs_the_steps_in_their_order() -> None:
    # The screens first: the grids are made of them; the walk-through and the chats then take
    # pictures of their own; the README's block last, from the transcripts.
    assert [(step.name, step.demo, step.browser) for step in showcase.STEPS] == [
        ("screens", True, True),
        ("compose", False, False),
        ("walk", True, True),
        ("chats", False, True),
        ("readme", False, False),
    ]


def shot(colour: str = "#0a0913", kind: str = "PNG") -> bytes:
    """A picture of the demo's device: 390×844 CSS px at DPR 2."""
    out = io.BytesIO()
    Image.new("RGB", (780, 1688), colour).save(out, kind)
    return out.getvalue()


async def test_the_screens_are_kept_as_webp_in_docs_images(
    run: showcase.Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    played: list[str] = []

    async def shoot(run: showcase.Run, lang: str, theme: str) -> dict[str, bytes]:
        played.append(f"{lang} {theme}")
        return {name: shot() for name in compose.SCREENS}

    monkeypatch.setattr(showcase, "_shoot_screens", shoot)
    run.langs, run.themes = ("ru", "en"), ("dark",)
    await showcase.draw_screens(run)
    assert played == ["ru dark", "en dark"]  # a browser of its own for each
    written = sorted(path.relative_to(run.images).as_posix() for path in run.written)
    assert written == sorted(
        compose.screen_file(name, "dark", lang) for name in compose.SCREENS for lang in run.langs
    )
    with Image.open(run.images / "screens" / "habit.dark.en.webp") as kept:
        assert (kept.format, kept.size) == ("WEBP", (780, 1688))


async def test_the_grids_are_made_of_the_screens_in_docs_images(run: showcase.Run) -> None:
    for name, colour in zip(compose.SCREENS, ("red", "green", "blue", "white"), strict=True):
        (run.images / "screens").mkdir(exist_ok=True)
        (run.images / compose.screen_file(name, "dark", "ru")).write_bytes(shot(colour, "WEBP"))
    await showcase.draw_compose(run)
    assert [path.name for path in run.written] == ["app.dark.webp"]
    with Image.open(run.images / "app.dark.webp") as grid:
        assert (grid.format, grid.mode, grid.width) == ("WEBP", "RGBA", compose.GRID_WIDTH)


async def test_the_walk_through_is_cut_from_its_scenes_with_a_still_of_the_first_frame(
    run: showcase.Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    played: list[str] = []

    async def record(run: showcase.Run, scene: walk.Scene, lang: str) -> list[walk.Frame]:
        played.append(scene.name)
        path = tmp_path / f"{scene.name}.jpg"
        path.write_bytes(shot(("red", "blue")[len(played) % 2], "JPEG"))
        return [walk.Frame(0.0, path)]

    monkeypatch.setattr(showcase, "_record", record)
    await showcase.draw_walk(run)
    assert played == [scene.name for scene in walk.SCENES]
    assert [path.name for path in run.written] == ["walkthrough.webp", "walkthrough.still.webp"]
    with Image.open(run.images / "walkthrough.webp") as made:
        assert (made.n_frames, made.width) == (len(walk.SCENES), 540)


async def test_the_walk_through_is_dark_only(
    run: showcase.Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def record(run: showcase.Run, scene: walk.Scene, lang: str) -> list[walk.Frame]:
        raise AssertionError("no scene is played in the light theme")

    monkeypatch.setattr(showcase, "_record", record)
    run.themes = ("light",)
    await showcase.draw_walk(run)
    assert run.written == []


def test_the_languages_and_themes_are_checked() -> None:
    args = showcase.parse(["all", "--lang", "en,ru", "--theme", "light"])
    assert (args.command, args.lang, args.theme) == ("all", ("ru", "en"), ("light",))
    defaults = showcase.parse([])
    assert (defaults.command, defaults.lang, defaults.theme) == (
        "all",
        ("ru", "en"),
        ("dark", "light"),
    )
    for wrong in (["--lang", "kk"], ["--theme", "dark,sepia"], ["--lang", ""]):
        with pytest.raises(SystemExit):
            showcase.parse(wrong)


def test_the_temporary_folder_goes_unless_it_is_kept(tmp_path: Path) -> None:
    with showcase.folder(None) as work:
        (work / "frame.jpg").write_bytes(b"jpeg")
        assert work.name.startswith("showcase-")
    assert not work.exists()
    with showcase.folder(tmp_path / "kept") as work:
        (work / "frame.jpg").write_bytes(b"jpeg")
    assert (tmp_path / "kept" / "frame.jpg").exists()


def loaded(modules: str) -> list[str]:
    """Which of aiohttp, the DevTools client and the server a fresh interpreter loads with
    `modules`."""
    probe = (
        f"import sys; import {modules}; "
        "print(sorted(m for m in ('aiohttp', 'scripts.showcase.cdp', 'scripts.showcase.serve') "
        "if m in sys.modules))"
    )
    answer = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, check=True
    )
    found: list[str] = json.loads(answer.stdout.strip().replace("'", '"'))
    return found


def test_what_ci_imports_loads_without_a_browser() -> None:
    # The modules CI's tests take, scripts/forecast_card.py among them, pull in neither the
    # DevTools client nor the server (spec §13.1), and those without the bot not even aiohttp.
    light = (
        "scripts.forecast_card, scripts.showcase.world, scripts.showcase.manifest, "
        "scripts.showcase.readme, scripts.showcase.chat_page, scripts.showcase.compose"
    )
    assert loaded(light) == []
    # The chats run the bot, and aiogram brings aiohttp along by itself: no browser all the same.
    assert loaded("scripts.showcase.chats") == ["aiohttp"]
