from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from scripts.showcase import __main__ as showcase
from scripts.showcase import manifest

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
    assert prepared[:2] == ["demo", "browser None"]


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


def test_what_ci_imports_loads_without_a_browser() -> None:
    # world.py feeds scripts/forecast_card.py and the manifest its test; neither may pull in the
    # DevTools client, the server or aiohttp (spec §13.1). A fresh interpreter sees what they load.
    probe = (
        "import sys; import scripts.forecast_card, scripts.showcase.world, "
        "scripts.showcase.manifest; "
        "print(sorted(m for m in ('aiohttp', 'scripts.showcase.cdp', 'scripts.showcase.serve') "
        "if m in sys.modules))"
    )
    answer = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert answer.stdout.strip() == "[]"
