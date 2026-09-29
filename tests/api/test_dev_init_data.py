from __future__ import annotations

from scripts.dev_init_data import build

from assistant.api.auth import verify_init_data
from tests.api.conftest import NOW, TOKEN


def test_dev_init_data_verifies() -> None:
    user = verify_init_data(build(5, "Dev", "en", TOKEN, NOW), TOKEN, NOW)
    assert (user.id, user.first_name, user.language_code) == (5, "Dev", "en")
