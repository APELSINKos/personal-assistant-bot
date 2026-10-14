"""What the generator relies on in the demo's build (spec §13.2, §6.4): where a shot of it is, the
emoji font it adds to the app, the hooks the walk-through holds on to, the story's habit and list
in the demo's data, and how a page shows it is ready for its picture (§13.1). The app gets no
test ids and no change for any of it.

`npm run build:demo` gives webapp/dist-demo, which the run serves at /demo/. With ?shot=1 its
page shows nothing but the device's screen, a rectangle of 390×844 CSS px, with the clock of ?at;
the app runs in a frame of the same origin, so a script of the page reaches into it.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.showcase.cdp import Page

AT = "2026-10-07T10:30"  # Wednesday in term, with classes: Moscow time in every shot
WIDTH, HEIGHT, SCALE = 390, 844, 2  # CSS px at DPR 2: 780×1688
FRAME = "iframe.tg-frame"  # the app's frame in the demo's page
EMOJI = "Showcase Emoji"
EMOJI_URL = "/showcase/fonts/Noto-COLRv1.ttf"  # on the run's server, the demo's own origin
SETTLE_TIME = 8.0  # seconds for a page to calm down before its picture
POLL = 0.05  # seconds between two looks at a busy page

# What the walk-through holds on to: today's classes of the app. A scene asks for a hook by its
# name and stops with that name when the app no longer has it.
HOOKS = {
    "tab": ".tab",  # a tab of the bar at the bottom
    "weather card": "a.card.weather-today",  # «Сегодня»: the weather, a link to «Погода»
    "hourly strip": ".strip",  # «Погода»: the 24 hours
    "habit toggle": "button.toggle",  # a habit's mark for today
    "habit link": "a.habit__open",  # «Привычки»: the way to a habit's own screen
    "money legend": ".legend__row",  # «Деньги»: a category under the ring
    "item check": "input.item__check",  # a checklist's item
}

# The story of the demo's data the pictures tell (spec §5.3, §23.4): its habit and its pinned
# shopping list, by their names in each language. Their ids are the demo's to give.
HABIT = {"ru": "Спорт", "en": "Sport"}
LIST = {"ru": "Покупки", "en": "Shopping"}


class DemoError(RuntimeError):
    """The demo's build is not what the generator relies on."""


class MissingHook(LookupError):
    """A hook of the walk-through the app no longer has."""


class ShotError(RuntimeError):
    """A page not fit for its picture: it scrolls sideways, shows an error or lost a font."""


class NotSettled(TimeoutError):
    """A page still busy after 8 s: a scene plays once more, as after any time out."""


def address(origin: str, route: str, lang: str, theme: str) -> str:
    """The demo's device on a route of the app, on the run's server."""
    return f"{origin}/demo/index.html?shot=1&at={AT}&lang={lang}&theme={theme}#{route}"


def emoji_css(font_url: str) -> str:
    """Noto's emoji after the app's own fonts, in the two variables every font-family of the app
    and of the demo's page goes through."""
    return (
        f'@font-face {{ font-family: "{EMOJI}"; src: url("{font_url}") format("truetype"); }}\n'
        f':root:root {{ --font-text: "Manrope", "{EMOJI}", system-ui, sans-serif; '
        f'--font-display: "Unbounded", "Manrope", "{EMOJI}", system-ui, sans-serif; }}'
    )


def emoji_script(font_url: str) -> str:
    """For Page.addScriptToEvaluateOnNewDocument: the emoji's style in every document of the tab,
    the demo's page and the app's frame, as soon as the document has its head."""
    return f"""(() => {{
  const add = () => {{
    const style = document.createElement("style");
    style.textContent = {json.dumps(emoji_css(font_url))};
    document.head.append(style);
  }};
  if (document.head) add();
  else document.addEventListener("DOMContentLoaded", add, {{ once: true }});
}})()"""


# The documents of the tab: the page and each frame of the same origin.
_DOCUMENTS = """const documents = () => [document, ...Array.from(
  document.querySelectorAll("iframe"), (frame) => frame.contentDocument).filter(Boolean)];"""

# Two frames drawn, but never a wait without end for a frame.
_FRAMES = """const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
  await Promise.race([frame().then(frame), new Promise((resolve) => setTimeout(resolve, 1000))]);"""

# Whether the emoji font is in each document: nothing, or what keeps it out; null without the
# app's frame.
_EMOJI_IN_PLACE = f"""(async () => {{
  {_DOCUMENTS}
  if (!document.querySelector({json.dumps(FRAME)})?.contentDocument) return null;
  for (const doc of documents()) {{
    const style = doc.defaultView.getComputedStyle(doc.documentElement);
    if (!style.getPropertyValue("--font-text").includes({json.dumps(EMOJI)})) {{
      return "its style was refused";
    }}
    try {{
      const faces = await doc.fonts.load('16px "{EMOJI}"', "\\u{{1F324}}");
      if (!faces.some((face) => face.status === "loaded")) return "the font was refused";
    }} catch {{
      return "the font was refused";
    }}
  }}
  return "";
}})()"""

# What keeps the page busy now, or nothing when it is calm.
_BUSY = f"""(() => {{
  {_DOCUMENTS}
  for (const doc of documents()) {{
    if (doc.fonts.status === "loading") return "a font is loading";
    if (doc.querySelector('[aria-busy="true"], .skeleton')) return "something is still loading";
    if (doc.querySelector(".tg-loading:not([hidden])")) return "the app has not said it is ready";
    const running = doc.getAnimations().some((animation) => animation.playState === "running"
      && animation.effect?.getComputedTiming().iterations !== Infinity);
    if (running) return "an animation is running";
  }}
  return "";
}})()"""

_TWO_FRAMES = f"""(async () => {{
  {_FRAMES}
}})()"""

# What makes a calm page unfit for its picture, or nothing.
_UNFIT = f"""(() => {{
  {_DOCUMENTS}
  for (const doc of documents()) {{
    const name = doc.location.pathname.split("/").pop() || "the page";
    const wide = doc.documentElement.scrollWidth > doc.defaultView.innerWidth;
    if (wide) return `${{name}} scrolls sideways`;
    if (doc.querySelector(".error-state")) return `${{name}} shows an error`;
    const failed = Array.from(doc.fonts).find((face) => face.status === "error");
    if (failed) return `${{name}}: the font ${{failed.family}} did not load`;
  }}
  return "";
}})()"""


# The ids of the story's habit and list in the data the demo's page serves its app (its host's
# api, as the app's own requests reach it); null for what it does not have, or without the host.
_STORY = """((habit, list) => {
  const host = window.__demoHost;
  if (!host) return null;
  const get = (path) => host.api({ method: "GET", path, search: "", body: null }).body;
  const habits = get("/habits"), notes = get("/notes");
  const found = (items, pick) => (Array.isArray(items) ? items.find(pick)?.id ?? null : null);
  return {
    habit: found(habits, (item) => item.name === habit),
    list: found(notes, (item) => item.pinned && item.text === list),
  };
})"""


async def story(page: Page, lang: str) -> dict[str, int]:
    """The ids of the story's habit and list in the demo the page shows: {"habit": 1, "list": 1}
    for the routes «/habits/{habit}» and «/notes/{list}»."""
    habit, shopping = HABIT[lang], LIST[lang]
    found = await page.evaluate(f"{_STORY}({json.dumps(habit)}, {json.dumps(shopping)})")
    if found is None:
        raise DemoError("the demo's page has no host for its app")
    if found["habit"] is None:
        raise DemoError(f"the demo's data have no habit «{habit}»")
    if found["list"] is None:
        raise DemoError(f"the demo's data have no pinned list «{shopping}»")
    return {"habit": int(found["habit"]), "list": int(found["list"])}


async def load(page: Page, origin: str, route: str, lang: str, theme: str, *, motion: bool) -> None:
    """Opens the demo's device on a route, the first thing a fresh tab does, as a phone shows it:
    390×844 CSS px at DPR 2, touch, no hover, a coarse pointer and Noto's emoji; without `motion`
    the app's entrance animations stay off (prefers-reduced-motion). Returns once the page has
    settled."""
    await page.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": WIDTH, "height": HEIGHT, "deviceScaleFactor": SCALE, "mobile": True},
    )
    await page.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
    media = [
        {"name": "hover", "value": "none"},
        {"name": "pointer", "value": "coarse"},
        {"name": "prefers-reduced-motion", "value": "no-preference" if motion else "reduce"},
    ]
    await page.send("Emulation.setEmulatedMedia", {"features": media})
    await page.send("Page.addScriptToEvaluateOnNewDocument", {"source": emoji_script(EMOJI_URL)})
    url = address(origin, route, lang, theme)
    await page.navigate(url)
    refused = await page.evaluate(_EMOJI_IN_PLACE)
    if refused is None:
        raise DemoError(f"the demo shows no app: {FRAME} is missing")
    if refused:
        # The demo's CSP lets in fonts of its origin and inline styles; should it stop doing so,
        # the pictures keep their emoji all the same.
        print(f"The demo's CSP kept the emoji out ({refused}): Page.setBypassCSP")
        await page.send("Page.setBypassCSP", {"enabled": True})
        await page.navigate("about:blank")
        await page.navigate(url)
        refused = await page.evaluate(_EMOJI_IN_PLACE)
        if refused:
            raise DemoError(f"the emoji font is not in the demo: {refused}")
    await settle(page)


async def go(page: Page, route: str) -> None:
    """Takes the app to another screen, as a link in it would: a new hash in its frame."""
    await page.evaluate(
        f"""(async () => {{
  document.querySelector({json.dumps(FRAME)}).contentWindow.location.hash = {json.dumps(route)};
  {_FRAMES}
}})()"""
    )
    await settle(page)


async def settle(page: Page) -> None:
    """Waits until the page is calm (§13.1): its fonts loaded, nothing loading (aria-busy,
    .skeleton, the device's own loader), no finite animation running, and still so after two
    more frames, which may start an animation or ask for a font; no longer than 8 s."""
    started = time.monotonic()
    while True:
        left = await page.evaluate(_BUSY)
        if not left:
            await page.evaluate(_TWO_FRAMES)
            left = await page.evaluate(_BUSY)
            if not left:
                return
        if time.monotonic() - started >= SETTLE_TIME:
            raise NotSettled(f"the page did not settle in {SETTLE_TIME:g} s: {left}")
        await asyncio.sleep(POLL)


async def check(page: Page) -> None:
    """What every picture of a page passes before it is taken (§13.1): the page has settled,
    nothing scrolls sideways, no error is on the screen and no font failed to load."""
    await settle(page)
    unfit = await page.evaluate(_UNFIT)
    if unfit:
        raise ShotError(unfit)


async def hook(page: Page, name: str) -> str:
    """The selector of a hook the app's frame shows now; MissingHook names one it does not."""
    selector = HOOKS[name]
    found = await page.evaluate(
        f"Boolean(document.querySelector({json.dumps(FRAME)})?.contentDocument"
        f"?.querySelector({json.dumps(selector)}))"
    )
    if not found:
        raise MissingHook(f"the demo shows no {name} ({selector}) on this screen")
    return selector
