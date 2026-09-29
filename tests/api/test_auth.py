from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest

from assistant.api.auth import AuthError, TelegramUser, verify_init_data
from tests.api.conftest import NOW, TOKEN, make_init_data


def test_valid_init_data() -> None:
    data = make_init_data(42, first_name="Саша", lang="en")
    assert verify_init_data(data, TOKEN, NOW) == TelegramUser(42, "Саша", "en")


def test_user_without_language_code() -> None:
    assert verify_init_data(make_init_data(lang=None), TOKEN, NOW).language_code is None


def test_signature_field_takes_part_in_the_check() -> None:
    data = make_init_data(extra={"signature": "abc"})
    assert verify_init_data(data, TOKEN, NOW).id == 1
    with pytest.raises(AuthError) as error:
        verify_init_data(data.replace("signature=abc", "signature=abd"), TOKEN, NOW)
    assert error.value.code == "invalid_init_data"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.replace("Alex", "Eve"),
        lambda s: s + "&extra=1",
        lambda s: s.split("&hash=")[0],
        lambda s: s + "&hash=00",
        lambda s: "",
        lambda s: "%%%",
    ],
)
def test_tampered_or_malformed(mutate: Callable[[str], str]) -> None:
    with pytest.raises(AuthError) as error:
        verify_init_data(mutate(make_init_data()), TOKEN, NOW)
    assert error.value.code == "invalid_init_data"


def test_signed_by_another_bot() -> None:
    with pytest.raises(AuthError):
        verify_init_data(make_init_data(token="999:OTHER-BOT"), TOKEN, NOW)


@pytest.mark.parametrize(
    ("age", "ok"),
    [
        (timedelta(hours=23, minutes=59), True),
        (timedelta(hours=24, seconds=1), False),
        (-timedelta(minutes=4), True),
        (-timedelta(minutes=6), False),
    ],
)
def test_age_window(age: timedelta, ok: bool) -> None:
    data = make_init_data(signed_at=NOW - age)
    if ok:
        assert verify_init_data(data, TOKEN, NOW).id == 1
    else:
        with pytest.raises(AuthError) as error:
            verify_init_data(data, TOKEN, NOW)
        assert error.value.code == "expired_init_data"
