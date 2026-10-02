"""What a habit looks like: an emoji from a fixed set and a colour from a fixed palette.

The set and the palette are closed on purpose: the share card draws every emoji from a bundled
PNG (assets/emoji) and every colour was checked for contrast in both themes of the app.
"""

from __future__ import annotations

from dataclasses import dataclass

DAILY = 7
DEFAULT_EMOJI = "🎯"
DEFAULT_COLOR = "mint"

# Eight per group: sport and body, food and health, mind and work, home and life.
EMOJI: tuple[str, ...] = (
    "💪", "🏃", "🚴", "🏊", "🧘", "🚶", "⚽", "🎾",
    "💧", "🥗", "🍎", "💊", "😴", "🦷", "🚭", "☕",
    "📚", "🧠", "💻", "🎸", "🎨", "📝", "🌍", "🎓",
    "🧹", "🌱", "🐕", "💰", "📵", "🙏", "🌅", "🎯",
)  # fmt: skip


@dataclass(frozen=True)
class Colour:
    dark: str  # on the dark theme and on the share card: >= 3:1 on its background and glows
    light: str  # on the light theme: >= 3:1 on its background and glows
    circle: str  # the bot shows a colour as this emoji


COLORS: dict[str, Colour] = {
    "mint": Colour("#7cf5c4", "#0b7a5c", "🟢"),
    "sky": Colour("#7cc8ff", "#1f6fb2", "🔵"),
    "violet": Colour("#b69cff", "#6b4fd8", "🟣"),
    "rose": Colour("#ff8fb1", "#c2306a", "🔴"),
    "coral": Colour("#ff9f7a", "#b8461f", "🟠"),
    "amber": Colour("#ffd28a", "#9a6200", "🟡"),
    "sand": Colour("#e0c9a6", "#86683d", "🟤"),
    "slate": Colour("#c3c7d6", "#5b6178", "⚪"),
}


def emoji_file(emoji: str) -> str:
    """The bundled PNG of an emoji, named as in googlefonts/noto-emoji: emoji_u1f4aa.png."""
    return "emoji_u" + "_".join(f"{ord(char):x}" for char in emoji) + ".png"
