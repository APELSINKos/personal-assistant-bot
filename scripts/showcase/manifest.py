"""showcase.json, the generator's record of the README's pictures (spec §13.8): the browser that
drew them, the commit the run started from, the size and SHA-256 of every file it wrote in
docs/images, the SHA-256 of each scene of a chat transcript as its pictures were drawn from it,
and the characters the machine's own fonts drew in them (§13.6). No address and no path outside
the repository: a file goes by its place in docs/images.

tests/unit/test_showcase_manifest.py holds docs/images to it, so a regeneration left halfway, a
picture changed by hand or a transcript edited without its pictures fails CI: the transcript test
checks the JSON against the bot, this record the pictures against the JSON. Nothing here needs a
browser.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

NAME = "showcase.json"
# What the generator writes in docs/images; the cards, the forecast and the cover there come from
# scripts of their own.
OWNED = ("screens/**/*", "chat/**/*", "app.*.webp", "walkthrough*.webp")
TRANSCRIPTS = "chat/*.json"


@dataclass(frozen=True)
class File:
    size: int
    sha256: str


@dataclass(frozen=True)
class Manifest:
    browser: str | None = None  # «Microsoft Edge 155.0.4283.45», of the last run that had one
    commit: str | None = None  # where the last run that wrote anything started from
    files: dict[str, File] = field(default_factory=dict)
    # Per transcript, per scene: the SHA-256 of the scene its pictures were drawn from.
    scenes: dict[str, dict[str, str]] = field(default_factory=dict)
    from_system_font: list[str] = field(default_factory=list)  # «U+21BB ↻»


def _file(path: Path) -> File:
    data = path.read_bytes()
    return File(len(data), hashlib.sha256(data).hexdigest())


def owned(images: Path) -> list[str]:
    """The generator's files in the images folder, by their place in it."""
    return sorted(
        {
            path.relative_to(images).as_posix()
            for pattern in OWNED
            for path in images.glob(pattern)
            if path.is_file()
        }
    )


def scene_sums(transcript: Mapping[str, Any]) -> dict[str, str]:
    """The SHA-256 of each scene of a transcript, a JSON object of the scenes by their names,
    over the scene's canonical JSON: keys sorted, no spaces, UTF-8."""
    return {
        name: hashlib.sha256(
            json.dumps(scene, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for name, scene in transcript.items()
    }


def load(images: Path) -> Manifest:
    data = json.loads((images / NAME).read_text(encoding="utf-8"))
    return Manifest(
        browser=data["browser"],
        commit=data["commit"],
        files={name: File(**entry) for name, entry in data["files"].items()},
        scenes=data["scenes"],
        from_system_font=data["from_system_font"],
    )


def save(images: Path, manifest: Manifest) -> None:
    text = json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (images / NAME).write_text(text, encoding="utf-8", newline="\n")


def record(
    images: Path,
    written: Iterable[Path],
    *,
    commit: str | None,
    browser: str | None = None,
    scenes: Mapping[str, dict[str, str]] | None = None,
    from_system_font: Sequence[str] | None = None,
) -> Manifest:
    """Records a run in showcase.json: the files it wrote, as they are now; the scenes it drew
    pictures of; the browser it used and the characters from the machine's fonts it found. What
    the run did not write or draw keeps its record, and a run that wrote nothing changes nothing."""
    mine, names = set(owned(images)), []
    for path in written:
        try:
            name = path.resolve().relative_to(images.resolve()).as_posix()
        except ValueError:
            raise ValueError(f"{path}: outside {images}") from None
        if name not in mine:
            raise ValueError(f"{name}: not a picture of the generator")
        names.append(name)
    if not (images / NAME).exists():
        save(images, Manifest())  # no run has drawn anything yet
    previous = load(images)
    if not names:
        return previous
    manifest = Manifest(
        browser=browser or previous.browser,
        commit=commit,
        files={**previous.files, **{name: _file(images / name) for name in names}},
        scenes={**previous.scenes, **(scenes or {})},
        from_system_font=(
            previous.from_system_font if from_system_font is None else list(from_system_font)
        ),
    )
    save(images, manifest)
    return manifest


def problems(images: Path) -> list[str]:
    """What is out of step between showcase.json and the files it records: nothing after a
    whole run."""
    if not (images / NAME).is_file():
        return [f"{NAME} is missing"]
    manifest, found = load(images), []
    for name, entry in sorted(manifest.files.items()):
        if not (images / name).is_file():
            found.append(f"{name}: in {NAME}, not on disk")
        elif _file(images / name) != entry:
            found.append(f"{name}: not the file {NAME} records")
    found += [
        f"{name}: on disk, not in {NAME}" for name in owned(images) if name not in manifest.files
    ]
    for path in sorted(images.glob(TRANSCRIPTS)):
        name = path.relative_to(images).as_posix()
        drawn = manifest.scenes.get(name)
        if drawn is None:
            found.append(f"{name}: no scene sums in {NAME}")
            continue
        now = scene_sums(json.loads(path.read_text(encoding="utf-8")))
        found += [
            f"{name}: scene {scene} is not the one its pictures were drawn from"
            for scene in sorted(now.keys() | drawn.keys())
            if now.get(scene) != drawn.get(scene)
        ]
    return found
