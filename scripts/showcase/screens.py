"""The four screens of the app the README's grids and the cover show (spec §13.3): «Сегодня»,
«Погода», the habit «Спорт» with its streak and year map, and «Деньги», as the demo's device
shows them at the frozen moment — Wednesday, 7 October 2026, 10:30 in Moscow, a day of classes.

Each theme and language gets a browser of its own, which opens the device as a phone: 390×844 CSS
px at DPR 2, touch, no hover, a coarse pointer and less motion, so that the app's entrances stay
off. A screen passes the checks of demo.check before its picture is taken, and the PNG is kept as
a WebP of quality 90 (method 6) in docs/images/screens, about 70–110 KB: the sources of the grids
and of the cover.
"""

from __future__ import annotations

import io
import struct
from typing import TYPE_CHECKING

from PIL import Image

from scripts.showcase import compose, demo

if TYPE_CHECKING:
    from scripts.showcase.cdp import Page

# The screens, in the grid's order, and the routes of the app they are on; {habit} is the id of
# the story's habit in the demo's data.
ROUTES = {"today": "/", "weather": "/weather", "habit": "/habits/{habit}", "money": "/money"}


async def shoot(page: Page, origin: str, lang: str, theme: str) -> dict[str, bytes]:
    """The PNG of each screen from a fresh tab, one route after another as the app's own links
    take it there."""
    await demo.load(page, origin, "/", lang, theme, motion=False)
    story = await demo.story(page, lang)
    here, shots = "/", {}
    for name in compose.SCREENS:
        route = ROUTES[name].format(**story)
        if route != here:
            await demo.go(page, route)
            here = route
        await demo.check(page)
        png = await page.screenshot(format="png")
        size = struct.unpack(">II", png[16:24])
        if size != (demo.WIDTH * demo.SCALE, demo.HEIGHT * demo.SCALE):
            raise demo.ShotError(f"{name}: a picture of {size[0]}×{size[1]}, not of the device")
        shots[name] = png
    return shots


def encode(png: bytes, name: str) -> bytes:
    """A screen's PNG as the WebP kept in docs/images."""
    with Image.open(io.BytesIO(png)) as shot:
        return compose.picture(shot.convert("RGB"), name)
