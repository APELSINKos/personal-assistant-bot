"""The README's walk-through (spec §13.5): five short scenes of the app in the dark theme, cut
together into an animated WebP of about 12 s that loops; its first frame is the still for those
who ask for less motion.

Each scene plays in a browser of its own — a long session slows down and then hangs — on the
demo's device at the frozen moment, with motion allowed, and is recorded once the page has
settled; the scenes after the first that show «Спорт» find it done, as the first leaves it. It
acts through the DOM, twice at most, and each act draws its touch: a ring that grows and fades
where a finger taps, then click(); where a finger drags, a dot moved in the same step of each
frame as the strip or the page it moves (the browser's smooth scroll ended 0.2 s before a dot's
own transition did, measured). The frames come from polling Page.captureScreenshot, JPEG at
about 25 a second at 780×1688, each stamped with the middle of its request:
Page.startScreencast sends 1× frames and stops sending them after about 6 s (measured).

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
    start: str  # the route it plays on; {list} is the id of the story's list
    length: float  # seconds
    acts: tuple[Act, ...]
    before: tuple[str, ...] = ()  # hooks the first screen shows besides those it acts on
    after: tuple[str, ...] = ()  # hooks the last screen shows
    # The route it opens on first when it needs the story: there the demo gives the story's ids
    # and, when `done`, marks the habit before the start asks for it. That screen asks for none
    # of the start's data, which the app would keep for 30 s and show without the mark.
    via: str = ""
    done: bool = False  # the story's habit done today, as the first scene leaves it


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
    # «Привычки», «Спорт» done: it opens on its streak and year map, «‹ Назад» in the header.
    Scene(
        "habit",
        "/habits",
        2.3,
        (Act(0.5, "tap", "habit link", demo.HABIT),),
        via="/",
        done=True,
    ),
    # The tab «Деньги» from «Сегодня», «Спорт» done: the cards rise and the ring by category
    # appears.
    Scene(
        "money",
        "/",
        2.1,
        (Act(0.2, "tap", "tab", "/money"),),
        after=("money legend",),
        via="/habits",
        done=True,
    ),
    # The pinned list «Покупки»: the first item still open is ticked.
    Scene(
        "list",
        "/notes/{list}",
        1.6,
        (Act(0.6, "tap", "item check", only=":not(:checked)"),),
        via="/",
    ),
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
  transition: opacity 0.25s;
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
  // A finger laid on at (x, y) that drags `by` px along `axis`: move(px) takes what it drags as
  // far, and the dot goes with it in the same step of each frame, 0.5 s, slow at both ends. An
  // error in a step fails the slide at once.
  const slide = async (x, y, axis, by, move) => {
    const dot = touch("finger", x, y);
    await wait(60);
    const start = performance.now();
    await new Promise((resolve, reject) => {
      const step = (now) => {
        try {
          const t = Math.min(Math.max((now - start) / 500, 0), 1);
          const moved = (by * (1 - Math.cos(Math.PI * t))) / 2;
          move(moved);
          dot.style.transform = `translate${axis}(${-moved}px)`;
          if (t < 1) requestAnimationFrame(step);
          else resolve();
        } catch (error) {
          reject(error);
        }
      };
      requestAnimationFrame(step);
    });
    lift(dot);
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
      const from = target.scrollLeft;
      const far = Math.min(by, target.scrollWidth - target.clientWidth - from);
      // The finger's way is centred on the strip, so it starts and ends on it.
      const x = outer.left + box.left + (box.width + far) / 2;
      await slide(x, outer.top + box.top + box.height * 0.6, "X", far, (moved) =>
        target.scrollTo({ left: from + moved, behavior: "instant" }));
      return true;
    },
    async scroll(selector, which) {
      const target = find(selector, which);
      if (!target) return false;
      const view = frame().contentWindow;
      const box = target.getBoundingClientRect();
      const from = view.scrollY;
      const end = view.document.documentElement.scrollHeight - view.innerHeight - from;
      const centred = Math.round(box.top + box.height / 2 - view.innerHeight / 2);
      const by = Math.max(0, Math.min(centred, end));
      const outer = frame().getBoundingClientRect();
      const x = outer.left + outer.width * 0.62;
      await slide(x, outer.top + outer.height * 0.75, "Y", by, (moved) =>
        view.scrollTo({ top: from + moved, behavior: "instant" }));
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
    """Plays a scene in a fresh tab and keeps its frames in `folder`, each with its time. The
    screen it starts on passes demo.check before the recording, and so does the screen its acts
    lead to after it."""
    await demo.load(page, origin, scene.via or scene.start, lang, THEME, motion=True)
    if scene.via:  # the story's ids are the demo's to give
        story = await demo.story(page, lang)
        if scene.done:
            await demo.mark(page, story["habit"])
        await demo.go(page, scene.start.format(**story))
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
    await demo.check(page)  # after keep(): frames of a screen that fails are there for --keep
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
    compose.WALK_WIDTH wide, and how long each one stays: a tick that shows the picture of the
    tick before makes that frame one tick longer."""
    images: list[Image.Image] = []
    counts: list[int] = []
    shown = b""  # the capture of the last tick
    for frames, length in scenes:
        for index in ticks([frame.time for frame in frames], length):
            data = frames[index].path.read_bytes()
            if data != shown:  # the same capture again needs no framing to be the same picture
                shown = data
                with Image.open(io.BytesIO(data)) as shot:
                    framed = compose.phone(shot.convert("RGB"), THEME)
                framed = compose.shrink(framed, compose.WALK_WIDTH)
                if not images or framed.tobytes() != images[-1].tobytes():
                    images.append(framed)
                    counts.append(0)
            counts[-1] += 1
    return images, durations(counts)
