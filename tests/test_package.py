from __future__ import annotations

import json
import tomllib
from pathlib import Path

import assistant
import assistant.bot
import assistant.bot.routers
import assistant.core
import assistant.core.clients
import assistant.core.services

ROOT = Path(__file__).resolve().parents[1]


def test_version_is_v2_6() -> None:
    assert assistant.__version__.startswith("2.7.0")


def test_every_file_that_carries_the_version_agrees() -> None:
    version = assistant.__version__
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == version
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    ours = [item for item in lock["package"] if item["name"] == "personal-assistant-bot"]
    assert [item["version"] for item in ours] == [version]
    manifest = json.loads((ROOT / "webapp" / "package.json").read_text(encoding="utf-8"))
    assert manifest["version"] == version
    npm_lock = json.loads((ROOT / "webapp" / "package-lock.json").read_text(encoding="utf-8"))
    # npm keeps the version twice: at the top and in the entry of the project itself ("").
    assert npm_lock["version"] == version
    assert npm_lock["packages"][""]["version"] == version


def test_subpackages_import_cleanly() -> None:
    assert assistant.bot is not None
    assert assistant.bot.routers is not None
    assert assistant.core is not None
    assert assistant.core.clients is not None
    assert assistant.core.services is not None
