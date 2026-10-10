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
import shutil
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from scripts.showcase import cdp, fonts, manifest, serve

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
        """Writes a file of docs/images, and nothing outside it, for the manifest."""
        path = self.images / name
        if not path.resolve().is_relative_to(self.images.resolve()):
            raise ValueError(f"{name}: outside docs/images")
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


# The steps of `all` in their order (spec §13.1): screens, compose, walk, chats, readme. Each also
# runs alone by its name.
STEPS: tuple[Step, ...] = ()


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
        if any(step.demo for step in steps):
            build_demo()
        if any(step.browser for step in steps):
            run.browser = cdp.find(browser)
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
    args = parse(argv)
    steps = STEPS if args.command == "all" else [s for s in STEPS if s.name == args.command]
    with folder(args.keep) as work:
        generate(steps, Run(args.lang, args.theme, work), browser=args.browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
