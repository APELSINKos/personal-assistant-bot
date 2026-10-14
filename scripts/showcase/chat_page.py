"""A scene of a chat transcript as a page for the browser to draw (spec §13.6). It looks like a chat
in Telegram but carries no mark of it — no logo, no name, none of its wallpapers, no header and no
avatar — on a dark (#0e1621) or a soft grey-green background: bubbles in and out with their
tails and times, two ticks on the user's (an SVG: neither font has «✓»), a date pill where the
day changes, a message's buttons as wide as its bubble in the rows they were sent in, the menu as
a grid of two columns, addresses coloured as links. Plain HTML and CSS without a script; the text
is escaped and keeps its spaces and lines, the leading ones of the habits' strips among them.

The fonts come from the run's own server: Roboto for the text, as Telegram on Android draws it,
and Noto's colour emoji. A page is 390 CSS px wide and as tall as its chat; shoot() takes it at
DPR 2. Nothing here needs a browser until shoot() is called with one.
"""

from __future__ import annotations

import html as markup
import re
import struct
from datetime import date
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from assistant.core.i18n import format_day
from scripts.showcase import demo, fonts

if TYPE_CHECKING:
    from scripts.showcase.cdp import Page

WIDTH = 390  # CSS px; the pictures are twice as wide
FONTS = "/showcase/fonts/"  # on the run's server
TEXT_FILE, EMOJI_FILE = quote(fonts.TEXT.file), quote(fonts.EMOJI.file)
# An address as Telegram marks one: a link of any scheme, or a name with a usual ending.
_ADDRESS = re.compile(
    r'\b[a-z][a-z0-9+.-]*://[^\s)»"]+'
    r'|\b(?:[a-z0-9-]+\.)+(?:com|org|net|ru|io|me)\b(?:/[^\s)»"]*)?',
    re.IGNORECASE,
)
_TAIL = (
    '<svg class="tail" viewBox="0 0 9 15" aria-hidden="true">'
    '<path d="M9 0C9 7.5 6 12.5 0 15h9z"/></svg>'
)
_TICKS = (
    '<svg class="ticks" viewBox="0 0 17 10" aria-hidden="true"><path d="M1 5.4l2.9 3 5.7-6.6'
    'M7.2 8.4l.6.4 8-7.2" fill="none" stroke="currentColor" stroke-width="1.4" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_STYLE = (
    '@font-face { font-family: "Showcase Text"; src: url("' + FONTS + TEXT_FILE + '") '
    'format("truetype"); font-weight: 100 900; font-stretch: 75% 100%; }\n'
    '@font-face { font-family: "Showcase Emoji"; src: url("' + FONTS + EMOJI_FILE + '") '
    'format("truetype"); }\n'
    """.dark { --page: #0e1621; --in: #182533; --out: #2b5278; --text: #f5f5f5; --time-in: #8a9aab;
  --time-out: #a8c8e8; --link: #71b7f5; --button: #1f2d3b; --button-text: #f5f5f5;
  --pill: #1e2c3a; --pill-text: #e8eef4; --panel: #17212b; --key: #243142; --key-text: #f5f5f5; }
.light { --page: #c9d6bc; --in: #ffffff; --out: #e2f7d0; --text: #111111; --time-in: #66717d;
  --time-out: #337636; --link: #1767a8; --button: #587852; --button-text: #ffffff;
  --pill: #587852; --pill-text: #ffffff; --panel: #f2f4f2; --key: #ffffff; --key-text: #1a1a1a; }
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--page); }
body { width: 390px; color: var(--text); font: 400 16px/1.35 "Showcase Text", "Showcase Emoji",
  sans-serif; -webkit-font-smoothing: antialiased; }
main { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px 12px; }
.message { display: flex; flex-direction: column; gap: 4px; max-width: 344px; }
.message.in { align-self: flex-start; }
.message.out { align-self: flex-end; }
.bubble { position: relative; padding: 6px 9px 7px 10px; border-radius: 15px;
  background: var(--in); }
.out .bubble { background: var(--out); }
.in .tailed { border-bottom-left-radius: 0; }
.out .tailed { border-bottom-right-radius: 0; }
.tail { position: absolute; bottom: 0; width: 9px; height: 15px; }
.in .tail { left: -8px; fill: var(--in); }
.out .tail { right: -8px; fill: var(--out); transform: scaleX(-1); }
.text { white-space: pre-wrap; overflow-wrap: anywhere; }
.link { color: var(--link); }
.spacer { display: inline-block; width: 42px; height: 1px; }
.out .spacer { width: 60px; }
.meta { position: absolute; right: 9px; bottom: 6px; display: flex; align-items: center; gap: 3px;
  font-size: 12px; line-height: 14px; color: var(--time-in); }
.out .meta { color: var(--time-out); }
.ticks { width: 17px; height: 10px; }
.keyboard { display: flex; flex-direction: column; gap: 4px; }
/* The buttons of a row are equal, and the row is as wide as its widest label wants. */
.row, .keys { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 4px; }
.button, .key { overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  text-align: center; }
.button { padding: 10px 6px; border-radius: 10px; background: var(--button);
  color: var(--button-text); font-size: 14px; font-weight: 500; line-height: 20px; }
.pill { align-self: center; margin: 4px 0; padding: 3px 10px; border-radius: 12px;
  background: var(--pill); color: var(--pill-text); font-size: 14px; font-weight: 500; }
.menu { display: flex; flex-direction: column; gap: 6px; padding: 7px 6px 9px;
  background: var(--panel); }
.keys { gap: 6px; }
.key { padding: 12px 6px; border-radius: 8px; background: var(--key); color: var(--key-text);
  font-size: 15px; line-height: 20px; box-shadow: 0 1px 0 rgba(0, 0, 0, 0.16); }
"""
)
# Whether both fonts are in: nothing, or the one that did not load.
_FONTS_IN = """(async () => {
  const fonts = [['16px "Showcase Text"', "Aа"], ['16px "Showcase Emoji"', "\\u{1F324}"]];
  for (const [font, sample] of fonts) {
    const faces = await document.fonts.load(font, sample);
    if (!faces.some((face) => face.status === "loaded")) return font;
  }
  return "";
})()"""


def pill(at: str, lang: str) -> str:
    """The date pill of a moment of the transcript: «8 октября» / «October 8»."""
    return format_day(date.fromisoformat(at[:10]), lang)


def _escape(text: str) -> str:
    return markup.escape(text, quote=False)


def _text(text: str) -> str:
    """Escaped, with each address marked as a link."""
    parts, start = [], 0
    for found in _ADDRESS.finditer(text):
        link = f'<span class="link">{_escape(found.group(0))}</span>'
        parts += [_escape(text[start : found.start()]), link]
        start = found.end()
    parts.append(_escape(text[start:]))
    return "".join(parts)


def _message(message: dict[str, Any], tailed: bool) -> str:
    side = "out" if message["from"] == "user" else "in"
    meta = message["at"][11:16] + (_TICKS if side == "out" else "")
    bubble = (
        f'<div class="bubble{" tailed" if tailed else ""}"><span class="text">'
        f'{_text(message["text"])}</span><span class="spacer"></span>'
        f'<span class="meta">{meta}</span>{_TAIL if tailed else ""}</div>'
    )
    rows = "".join(
        '<div class="row">'
        + "".join(f'<span class="button">{_escape(label)}</span>' for label in row)
        + "</div>"
        for row in message["inline"]
    )
    keyboard = f'<div class="keyboard">{rows}</div>' if rows else ""
    return f'<div class="message {side}">{bubble}{keyboard}</div>'


def html(scene: dict[str, Any], lang: str, theme: str) -> str:
    """The page of a scene in a theme, «dark» or «light»."""
    messages, parts = scene["messages"], []
    for index, message in enumerate(messages):
        day = message["at"][:10]
        if index and messages[index - 1]["at"][:10] != day:
            parts.append(f'<div class="pill">{_escape(pill(message["at"], lang))}</div>')
        after = messages[index + 1] if index + 1 < len(messages) else None
        tailed = after is None or after["from"] != message["from"] or after["at"][:10] != day
        parts.append(_message(message, tailed))
    menu = ""
    if scene.get("menu"):
        rows = "".join(
            '<div class="keys">'
            + "".join(f'<span class="key">{_escape(key)}</span>' for key in row)
            + "</div>"
            for row in scene["menu"]
        )
        menu = f'<footer class="menu">{rows}</footer>'
    return (
        f'<!doctype html>\n<html lang="{lang}" class="{theme}">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{lang} {theme}</title>\n<style>\n{_STYLE}</style>\n</head>\n<body>\n"
        f"<main>{''.join(parts)}</main>{menu}\n</body>\n</html>\n"
    )


def texts(scene: dict[str, Any], lang: str) -> list[str]:
    """Every text the page of a scene draws: messages, times, buttons, date pills, the menu."""
    drawn = []
    for index, message in enumerate(scene["messages"]):
        if index and scene["messages"][index - 1]["at"][:10] != message["at"][:10]:
            drawn.append(pill(message["at"], lang))
        drawn += [message["text"], message["at"][11:16]]
        drawn += [label for row in message["inline"] for label in row]
    return drawn + [key for row in scene.get("menu", []) for key in row]


async def shoot(page: Page, url: str) -> bytes:
    """The PNG of a chat page: 390 CSS px wide at DPR 2, as tall as the chat, once its fonts are
    in and it has settled (demo.check)."""
    metrics = {"width": WIDTH, "height": 844, "deviceScaleFactor": demo.SCALE, "mobile": False}
    await page.send("Emulation.setDeviceMetricsOverride", metrics)
    await page.navigate(url)
    missing = await page.evaluate(_FONTS_IN)
    if missing:
        raise demo.ShotError(f"{url}: the font {missing} did not load")
    # The chat's own height: the document is never shorter than the window.
    height = await page.evaluate("Math.ceil(document.body.getBoundingClientRect().height)")
    await page.send("Emulation.setDeviceMetricsOverride", {**metrics, "height": height})
    await demo.check(page)
    png = await page.screenshot(format="png")
    size = struct.unpack(">II", png[16:24])
    if size != (WIDTH * demo.SCALE, height * demo.SCALE):
        raise demo.ShotError(f"{url}: a picture of {size[0]}×{size[1]}, not of the whole chat")
    return png
