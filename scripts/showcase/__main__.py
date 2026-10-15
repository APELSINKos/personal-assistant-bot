"""Draw the README's pictures of the app and of the bot.

Usage:  uv run python -m scripts.showcase [all|STEP] [--lang ru,en] [--theme dark,light]
                                          [--browser PATH] [--keep FOLDER]

The app's pictures come from the demo's build (npm run build:demo) in a headless Edge or Chrome,
the bot's from its own code with made-up data, and Pillow does the rest (spec §13). A run writes
docs/images/** and the «В чате» blocks of the two READMEs, nothing else, and never reads .env.
It records what it wrote in docs/images/showcase.json, which CI holds the pictures to; a run that
fails records nothing, so a regeneration left halfway shows there.

It needs Edge or Chrome (--browser, else SHOWCASE_BROWSER, else the usual places), Node for the
demo's build and the network for the first download of its two fonts. Temporary files go to a
showcase-… folder in the system's temporary folder and are removed at the end; --keep FOLDER
puts them there instead and keeps them.

Redraw for a release that changes the bot's messages in the scenes (CI says so) or the look of
the four screens or of the scenes of the animation (CI cannot see that): `all`, then
scripts/cover.py, then the repository's social preview by hand. A full redraw adds about 5.5 MB
to the history for good, so all the pictures of a release come from one run.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import functools
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from scripts.showcase import (
    cdp,
    chat_page,
    chats,
    compose,
    fonts,
    manifest,
    readme,
    screens,
    serve,
    walk,
)

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"
WEBAPP = ROOT / "webapp"
LANGS = ("ru", "en")
THEMES = ("dark", "light")


@dataclass
class Run:
    """What the steps of a run share, and what they leave for the manifest."""

    langs: tuple[str, ...]
    themes: tuple[str, ...]
    work: Path  # the run's temporary folder: profiles, frames, pages
    images: Path = IMAGES
    readmes: Path = ROOT  # where README.md and README.en.md are
    browser: Path | None = None  # Edge or Chrome, for the steps that take pictures
    server: serve.Server | None = None  # /demo/ and /showcase/ for the browser
    written: list[Path] = field(default_factory=list)
    used: str | None = None  # «Microsoft Edge 155.0.4283.45», once a browser has run
    scenes: dict[str, dict[str, str]] = field(default_factory=dict)  # drawn from the transcripts
    from_system_font: list[str] | None = None

    @property
    def pages(self) -> Path:
        """The generator's own pages, served at /showcase/."""
        return self.work / "pages"

    def write(self, name: str, data: bytes) -> Path:
        """Writes one of the generator's files of docs/images, for the manifest. Anything else,
        outside the folder or another script's picture in it, is refused before a byte is
        written."""
        path, images = (self.images / name).resolve(), self.images.resolve()
        if not path.is_relative_to(images):
            raise ValueError(f"{name}: outside docs/images")
        if not manifest.owns(path.relative_to(images).as_posix()):
            raise ValueError(f"{name}: not a picture of the generator")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.written.append(path)
        print(f"{name}: {len(data) // 1024} KB")
        return path

    @contextlib.asynccontextmanager
    async def launch(self) -> AsyncIterator[cdp.Browser]:
        """A fresh browser for a scene; the manifest names it."""
        assert self.browser is not None, "a step that takes pictures says so"
        async with cdp.launch(self.browser, self.work) as browser:
            self.used = self.used or await browser.version()
            yield browser


@dataclass(frozen=True)
class Step:
    name: str
    draw: Callable[[Run], Awaitable[None]]
    demo: bool = False  # it shows the demo's build
    browser: bool = False  # it takes pictures in a browser


async def draw_screens(run: Run) -> None:
    """The demo's four screens (spec §13.3) in each language and theme, each pair in a browser
    of its own: the sources of the grids and of the cover."""
    for lang in run.langs:
        for theme in run.themes:
            play = functools.partial(_shoot_screens, run, lang, theme)
            for name, png in (await cdp.scene(f"screens {lang} {theme}", play)).items():
                file = compose.screen_file(name, theme, lang)
                run.write(file, screens.encode(png, file))


async def _shoot_screens(run: Run, lang: str, theme: str) -> dict[str, bytes]:
    assert run.server is not None, "a step that takes pictures has the server"
    async with run.launch() as browser:
        return await screens.shoot(await browser.page(), run.server.origin, lang, theme)


async def draw_compose(run: Run) -> None:
    """The grids of four phones (spec §13.4) from the screens in docs/images, as CI makes them
    again to check them."""
    for lang in run.langs:
        for theme in run.themes:
            shots = []
            for name in compose.SCREENS:
                with Image.open(run.images / compose.screen_file(name, theme, lang)) as shot:
                    shots.append(shot.convert("RGB"))
            file = compose.grid_file(theme, lang)
            run.write(file, compose.picture(compose.grid(shots, theme), file))


async def draw_walk(run: Run) -> None:
    """The walk-through (spec §13.5) in each language, dark only: its scenes, each played in a
    browser of its own, cut together; and its first frame as the still."""
    if walk.THEME not in run.themes:
        print("The walk-through is dark only: nothing to draw in the light theme")
        return
    for lang in run.langs:
        clips = []
        for scene in walk.SCENES:
            play = functools.partial(_record, run, scene, lang)
            clips.append((await cdp.scene(f"walk {lang} {scene.name}", play), scene.length))
        frames, durations = walk.assemble(clips)
        run.write(compose.walk_file(lang), compose.animation(frames, durations))
        still = compose.still_file(lang)
        run.write(still, compose.picture(frames[0], still, compose.STILL_QUALITY))


async def _record(run: Run, scene: walk.Scene, lang: str) -> list[walk.Frame]:
    assert run.server is not None, "a step that takes pictures has the server"
    async with run.launch() as browser:
        folder = run.work / "walk" / lang / scene.name  # kept with --keep
        return await walk.record(await browser.page(), run.server.origin, scene, lang, folder)


async def draw_chats(run: Run) -> None:
    """The bot's messages (spec §13.6): each language's transcript, recorded from the bot, then a
    page and a picture of each scene in each theme, in a browser of its own per language and
    theme. The scenes' sums go to the manifest only when every theme was drawn: a picture of the
    other theme would still show the transcript before."""
    recorded = {lang: await chats.record(lang) for lang in run.langs}
    for lang, scenes in recorded.items():
        run.write(readme.TRANSCRIPT[lang], chats.dump(scenes).encode())
    run.from_system_font = _from_system_font(run.images)
    if run.from_system_font:
        print("Drawn in the machine's own fonts:", ", ".join(run.from_system_font))
    run.pages.mkdir(parents=True, exist_ok=True)
    for lang, scenes in recorded.items():
        for theme in run.themes:
            pages = {scene: f"chat-{lang}-{theme}-{scene}.html" for scene in scenes}
            for scene, shown in scenes.items():
                page = chat_page.html(shown, lang, theme)
                (run.pages / pages[scene]).write_text(page, encoding="utf-8")
            play = functools.partial(_shoot_chats, run, pages)
            for scene, png in (await cdp.scene(f"chats {lang} {theme}", play)).items():
                file = readme.picture(scene, theme, lang)
                run.write(file, _lossless(png, file))
        if set(run.themes) == set(THEMES):
            run.scenes[readme.TRANSCRIPT[lang]] = manifest.scene_sums(scenes)


async def _shoot_chats(run: Run, pages: dict[str, str]) -> dict[str, bytes]:
    assert run.server is not None, "a step that takes pictures has the server"
    async with run.launch() as browser:
        tab = await browser.page()
        return {
            scene: await chat_page.shoot(tab, run.server.url(f"/showcase/{name}"))
            for scene, name in pages.items()
        }


def _lossless(png: bytes, name: str) -> bytes:
    """A shot as a lossless WebP, which the flat colours of a chat keep small, within the budget
    of one picture."""
    out = io.BytesIO()
    with Image.open(io.BytesIO(png)) as shot:
        shot.convert("RGB").save(out, "WEBP", lossless=True, quality=100, method=6)
    data = out.getvalue()
    if len(data) > compose.PICTURE_BUDGET:
        raise compose.BudgetError(f"{name}: {len(data)} bytes, over {compose.PICTURE_BUDGET}")
    return data


def _from_system_font(images: Path) -> list[str]:
    """The characters the chat pictures take from the machine's own fonts, Roboto and Noto
    having none of them (§13.6), over every transcript in docs/images/chat: «U+21BB ↻»."""
    have = [fonts.coverage(fonts.fetch(font)) for font in fonts.FONTS]
    drawn: list[str] = []
    for lang, name in readme.TRANSCRIPT.items():
        if (images / name).is_file():
            scenes = json.loads((images / name).read_text(encoding="utf-8"))
            drawn += [text for scene in scenes.values() for text in chat_page.texts(scene, lang)]
    return [fonts.describe(char) for char in fonts.outside("".join(drawn), *have)]


async def draw_readme(run: Run) -> None:
    """The «В чате» blocks of the READMEs (spec §15.4), from the transcripts in docs/images/chat;
    nothing of a README but the text between its markers changes."""
    for lang in run.langs:
        transcript = json.loads((run.images / readme.TRANSCRIPT[lang]).read_text(encoding="utf-8"))
        path = run.readmes / readme.README[lang]
        changed = readme.write(path, readme.render(transcript, lang))
        print(f"{path.name}: the chat pictures' block {'written' if changed else 'as it was'}")


# The steps of `all` in their order (spec §13.1). Each also runs alone by its name: `compose`
# alone makes the grids again from the screens in docs/images.
STEPS: tuple[Step, ...] = (
    Step("screens", draw_screens, demo=True, browser=True),
    Step("compose", draw_compose),
    Step("walk", draw_walk, demo=True, browser=True),
    Step("chats", draw_chats, browser=True),
    Step("readme", draw_readme),
)


def build_demo() -> None:
    """npm ci when webapp has no node_modules yet, then npm run build:demo."""
    npm = shutil.which("npm")  # npm.cmd on Windows
    if npm is None:
        raise SystemExit("npm is not on PATH: the demo is built with Node")
    if not (WEBAPP / "node_modules").is_dir():
        subprocess.run([npm, "ci"], cwd=WEBAPP, check=True)
    subprocess.run([npm, "run", "build:demo"], cwd=WEBAPP, check=True)


def head() -> str | None:
    """The commit the run starts from."""
    try:
        answer = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return answer.stdout.strip() or None


@contextlib.contextmanager
def folder(keep: Path | None) -> Iterator[Path]:
    """The run's temporary folder: a showcase-… folder in the system's, removed at the end, or
    --keep's, kept with what the run left in it."""
    if keep is not None:
        keep.mkdir(parents=True, exist_ok=True)
        yield keep
        return
    work = Path(tempfile.mkdtemp(prefix="showcase-"))
    try:
        yield work
    finally:
        for _ in range(40):  # a file a browser has just let go of is free a moment later
            shutil.rmtree(work, ignore_errors=True)
            if not work.exists():
                break
            time.sleep(0.25)
        else:
            print(f"The run's temporary folder stays: {work}")


def generate(steps: Sequence[Step], run: Run, *, browser: str | None = None) -> None:
    """Runs the steps with what they need, then records what they wrote."""
    with ExitStack() as stack:
        pictures = any(step.browser for step in steps)
        if pictures:  # first: without a browser nothing is built or downloaded
            run.browser = cdp.find(browser)
        if any(step.demo for step in steps):
            build_demo()
        if pictures:
            for font in fonts.FONTS:
                fonts.fetch(font)
            routes = {
                "/demo/": WEBAPP / "dist-demo",
                "/showcase/": run.pages,
                "/showcase/fonts/": fonts.cache(),
            }
            run.server = stack.enter_context(serve.serve(routes))

        async def draw() -> None:
            for step in steps:
                await step.draw(run)

        asyncio.run(draw())
    manifest.record(
        run.images,
        run.written,
        commit=head(),
        browser=run.used,
        scenes=run.scenes,
        from_system_font=run.from_system_font,
    )


def _choices(allowed: tuple[str, ...]) -> Callable[[str], tuple[str, ...]]:
    def parse(text: str) -> tuple[str, ...]:
        asked = {part.strip() for part in text.split(",")} - {""}
        if not asked or not asked <= set(allowed):
            raise argparse.ArgumentTypeError(f"{text!r}: any of {','.join(allowed)}")
        return tuple(value for value in allowed if value in asked)

    return parse


def parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.showcase", description=__doc__.splitlines()[0]
    )
    names = ["all", *(step.name for step in STEPS)]
    parser.add_argument("command", nargs="?", default="all", choices=names)
    parser.add_argument("--lang", type=_choices(LANGS), default=LANGS, metavar="ru,en")
    parser.add_argument("--theme", type=_choices(THEMES), default=THEMES, metavar="dark,light")
    parser.add_argument(
        "--browser", metavar="PATH", help="Edge or Chrome to run, else SHOWCASE_BROWSER"
    )
    parser.add_argument(
        "--keep", type=Path, metavar="FOLDER", help="where to keep the temporary files"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        # Redirected on Windows, a stream writes the ANSI code page, which has no «↻»: such a
        # character is printed as its escape rather than stopping the run.
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
    args = parse(argv)
    steps = STEPS if args.command == "all" else [s for s in STEPS if s.name == args.command]
    with folder(args.keep) as work:
        generate(steps, Run(args.lang, args.theme, work), browser=args.browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
