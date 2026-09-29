from __future__ import annotations

import assistant
import assistant.bot
import assistant.bot.routers
import assistant.core
import assistant.core.clients
import assistant.core.services


def test_version_is_v2_dev() -> None:
    assert assistant.__version__.startswith("2.0.0")


def test_subpackages_import_cleanly() -> None:
    assert assistant.bot is not None
    assert assistant.bot.routers is not None
    assert assistant.core is not None
    assert assistant.core.clients is not None
    assert assistant.core.services is not None
