"""The README's walk-through (spec §13.5): five short scenes of the app in the dark theme, cut
together into an animated WebP of about 12 s that loops; its first frame is the still for those
who ask for less motion.

Each scene plays in a browser of its own — a long session slows down and then hangs — on the
demo's device at the frozen moment, with motion allowed, and is recorded once the page has
settled. It acts through the DOM, a click() or a smooth scroll, twice at most, and each act draws
its touch: a ring that grows and fades where a finger taps, a dot that travels with what a finger
drags. The frames come from polling Page.captureScreenshot, JPEG at about 25 a second at
780×1688, each stamped with the middle of its request: Page.startScreencast sends 1× frames and
stops sending them after about 6 s (measured).

The cut: each scene at 15 frames a second, the last frame taken at or before each tick; equal
neighbours become one longer frame; plain cuts between the scenes, as a crossfade adds 40 % of
weight and ghosts; each frame in compose.phone(), 540 px wide; and 0.9 s of rest on the last.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import shutil
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from scripts.showcase import compose, demo

if TYPE_CHECKING:
    from scripts.showcase.cdp import Page

THEME = "dark"
FPS = 15
REST = 0.9  # seconds on the last frame before the walk-through starts again


@dataclass(frozen=True)
class Act:
    at: float  # seconds into the scene
    kind: str  # "tap"; "drag", the hook sideways by `by` CSS px; "scroll", the screen to it
    hook: str  # a hook of demo.HOOKS
    which: str | Mapping[str, str] = ""  # what its label, address or words hold, by language
    only: str = ""  # narrows the hook: «:not(:checked)»
    by: int = 0


@dataclass(frozen=True)
class Scene:
    name: str
    start: str  # the route it opens on; {list} is the id of the story's list
    length: float  # seconds
    acts: tuple[Act, ...]
    before: tuple[str, ...] = ()  # hooks the first screen shows besides those it acts on
    after: tuple[str, ...] = ()  # hooks the last screen shows


@dataclass(frozen=True)
class Frame:
    time: float  # seconds into its scene: the middle of the request that took it
    path: Path


SCENES = (
    # «Сегодня»: the weather, the classes, today's plans; down to the habits, and «Спорт» is done.
    Scene(
        "today",
        "/",
        2.8,
        (
            Act(1.2, "scroll", "habit toggle", demo.HABIT),
            Act(1.8, "tap", "habit toggle", demo.HABIT),
        ),
        before=("weather card",),
    ),
    # «Погода»: the 24 hours dragged towards the evening and its rain.
    Scene("weather", "/weather", 2.4, (Act(0.8, "drag", "hourly strip", by=300),)),
    # «Привычки»: «Спорт» opens on its streak and year map, «‹ Назад» in the header.
    Scene("habit", "/habits", 2.3, (Act(0.5, "tap", "habit link", demo.HABIT),)),
    # The tab «Деньги»: the cards rise and the ring by category appears.
    Scene("money", "/", 2.1, (Act(0.2, "tap", "tab", "/money"),), after=("money legend",)),
    # The pinned list «Покупки»: the first item still open is ticked.
    Scene("list", "/notes/{list}", 1.6, (Act(0.6, "tap", "item check", only=":not(:checked)"),)),
)

_TOUCH_STYLE = """
.showcase-touch {
  position: fixed;
  z-index: 2147483647;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.28);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.75);
  pointer-events: none;
}
.showcase-touch--tap {
  width: 46px;
  height: 46px;
  margin: -23px 0 0 -23px;
  animation: showcase-tap 0.55s ease-out forwards;
}
.showcase-touch--finger {
  width: 40px;
  height: 40px;
  margin: -20px 0 0 -20px;
  transition: transform 0.5s ease-in-out, opacity 0.25s;
}
@keyframes showcase-tap {
  from { transform: scale(0.5); opacity: 1; }
  to { transform: scale(1.35); opacity: 0; }
}
"""

# The acts, run in the demo's page over the app's frame. Each finds its target in the frame — the
# first of its hook whose label, address or words hold `which` — draws its touch above the device
# and answers whether it found one.
_TOUCH = """(() => {
  if (window.__showcase) return;
  const style = document.createElement("style");
  style.textContent = STYLE;
  document.head.append(style);
  const frame = () => document.querySelector(FRAME);
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const says = (element) =>
    [element.getAttribute("aria-label"), element.getAttribute("href"), element.textContent];
  const find = (selector, which) =>
    Array.from(frame().contentDocument.querySelectorAll(selector)).find(
      (element) => !which || says(element).some((said) => said !== null && said.includes(which)),
    );
  const touch = (kind, x, y) => {
    const dot = document.createElement("div");
    dot.className = `showcase-touch showcase-touch--${kind}`;
    dot.style.left = `${x}px`;
    dot.style.top = `${y}px`;
    document.body.append(dot);
    return dot;
  };
  const lift = (dot) => {
    dot.style.opacity = "0";
    setTimeout(() => dot.remove(), 300);
  };
  window.__showcase = {
    async tap(selector, which) {
      const target = find(selector, which);
      if (!target) return false;
      const outer = frame().getBoundingClientRect();
      const box = target.getBoundingClientRect();
      const x = outer.left + box.left + box.width / 2;
      const ring = touch("tap", x, outer.top + box.top + box.height / 2);
      setTimeout(() => ring.remove(), 700);
      await wait(120);
      target.click();
      return true;
    },
    async drag(selector, which, by) {
      const target = find(selector, which);
      if (!target) return false;
      const outer = frame().getBoundingClientRect();
      const box = target.getBoundingClientRect();
      const y = outer.top + box.top + box.height * 0.6;
      const dot = touch("finger", outer.left + box.right - 60, y);
      await wait(60);
      dot.style.transform = `translateX(${-by}px)`;
      target.scrollBy({ left: by, behavior: "smooth" });
      await wait(560);
      lift(dot);
      return true;
    },
    async scroll(selector, which) {
      const target = find(selector, which);
      if (!target) return false;
      const view = frame().contentWindow;
      const box = target.getBoundingClientRect();
      const end = view.document.documentElement.scrollHeight - view.innerHeight - view.scrollY;
      const centred = Math.round(box.top + box.height / 2 - view.innerHeight / 2);
      const by = Math.max(0, Math.min(centred, end));
      const outer = frame().getBoundingClientRect();
      const dot = touch("finger", outer.left + outer.width * 0.62, outer.top + outer.height * 0.75);
      await wait(60);
      dot.style.transform = `translateY(${-by}px)`;
      view.scrollBy({ top: by, behavior: "smooth" });
      await wait(560);
      lift(dot);
      return true;
    },
  };
})()"""
TOUCH = _TOUCH.replace("STYLE", json.dumps(_TOUCH_STYLE)).replace("FRAME", json.dumps(demo.FRAME))


def target(act: Act, lang: str) -> tuple[str, str]:
    """The selector of the act's hook and what its target says, in `lang`."""
    which = act.which if isinstance(act.which, str) else act.which[lang]
    return demo.HOOKS[act.hook] + act.only, which


async def act(page: Page, act: Act, lang: str) -> None:
    """Plays an act; MissingHook names one the screen does not show."""
    selector, which = target(act, lang)
    found = await page.evaluate(
        f"window.__showcase.{act.kind}({json.dumps(selector)}, {json.dumps(which)}, {act.by})"
    )
    if not found:
        named = f"{act.hook} «{which}»" if which else act.hook
        raise demo.MissingHook(f"the demo shows no {named} ({selector}) on this screen")


async def record(page: Page, origin: str, scene: Scene, lang: str, folder: Path) -> list[Frame]:
    """Plays a scene in a fresh tab and keeps its frames in `folder`, each with its time."""
    opens = "/" if "{" in scene.start else scene.start
    await demo.load(page, origin, opens, lang, THEME, motion=True)
    if opens != scene.start:  # the story's list: its id is the demo's to give
        await demo.go(page, scene.start.format(**await demo.story(page, lang)))
    for hook in (*scene.before, *(item.hook for item in scene.acts)):
        await demo.hook(page, hook)
    await demo.check(page)
    await page.evaluate(TOUCH)
    shots: list[tuple[float, bytes]] = []
    began = time.monotonic()

    async def capture() -> None:
        while time.monotonic() - began < scene.length:
            asked = time.monotonic()
            data = await page.screenshot(format="jpeg", quality=90, optimizeForSpeed=True)
            shots.append(((asked + time.monotonic()) / 2 - began, data))

    capturing = asyncio.create_task(capture())
    try:
        for item in scene.acts:
            await asyncio.sleep(max(0.0, began + item.at - time.monotonic()))
            await act(page, item, lang)
        await capturing
    finally:
        if not capturing.done():
            capturing.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await capturing
    for hook in scene.after:
        await demo.hook(page, hook)
    frames = keep(shots, folder)
    print(f"walk {lang} {scene.name}: {len(frames)} frames in {scene.length:g} s")
    return frames


def keep(shots: Sequence[tuple[float, bytes]], folder: Path) -> list[Frame]:
    """A scene's frames as files in `folder`, which holds nothing else: not even what a first
    try of the scene left there."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    frames = []
    for number, (moment, data) in enumerate(shots):
        path = folder / f"{number:04d}.jpg"
        path.write_bytes(data)
        frames.append(Frame(moment, path))
    return frames


def ticks(times: Sequence[float], length: float) -> list[int]:
    """The frame each tick of a scene shows, FPS a second for `length` seconds: the last one
    taken at or before the tick, or the first one before any was."""
    shown, index = [], 0
    for tick in range(round(length * FPS)):
        while index + 1 < len(times) and times[index + 1] <= tick / FPS:
            index += 1
        shown.append(index)
    return shown


def durations(counts: Sequence[int]) -> list[int]:
    """How long each frame stays, in ms, for the ticks it lasts. Each ends at the tick it ends
    at, rounded once, so the frames add up to their ticks; the last one rests REST more."""
    out, tick = [], 0
    for count in counts:
        out.append(round((tick + count) * 1000 / FPS) - round(tick * 1000 / FPS))
        tick += count
    out[-1] += round(REST * 1000)
    return out


def assemble(
    scenes: Sequence[tuple[Sequence[Frame], float]],
) -> tuple[list[Image.Image], list[int]]:
    """The walk-through's frames from its scenes and their lengths, each in its phone,
    compose.WALK_WIDTH wide, and how long each one stays."""
    runs: list[tuple[bytes, int]] = []  # a captured JPEG and the ticks it stays
    read: dict[Path, bytes] = {}
    for frames, length in scenes:
        for index in ticks([frame.time for frame in frames], length):
            path = frames[index].path
            data = read.setdefault(path, path.read_bytes())
            if runs and runs[-1][0] == data:
                runs[-1] = (data, runs[-1][1] + 1)
            else:
                runs.append((data, 1))
    images: list[Image.Image] = []
    counts: list[int] = []
    for data, count in runs:
        with Image.open(io.BytesIO(data)) as shot:
            framed = compose.shrink(compose.phone(shot.convert("RGB"), THEME), compose.WALK_WIDTH)
        if images and framed.tobytes() == images[-1].tobytes():
            counts[-1] += count
        else:
            images.append(framed)
            counts.append(count)
    return images, durations(counts)
