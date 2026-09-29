"""Telegram Mini App initData: verification for requests, signing for tests and development."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode

MAX_AGE = timedelta(hours=24)
MAX_CLOCK_SKEW = timedelta(minutes=5)


class AuthError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str | None
    language_code: str | None


def _secret(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def _digest(fields: Mapping[str, str], bot_token: str) -> str:
    # Every field except "hash" — "signature" included — sorted by key, one "k=v" per line.
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    return hmac.new(_secret(bot_token), check_string.encode(), hashlib.sha256).hexdigest()


def sign_init_data(fields: Mapping[str, str], bot_token: str) -> str:
    return urlencode({**fields, "hash": _digest(fields, bot_token)})


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def verify_init_data(init_data: str, bot_token: str, now: datetime) -> TelegramUser:
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise AuthError("invalid_init_data") from error
    fields = dict(pairs)
    received = fields.pop("hash", "")
    if len(fields) + 1 != len(pairs) or not received:
        raise AuthError("invalid_init_data")  # no hash, or a key sent twice
    if not hmac.compare_digest(_digest(fields, bot_token).encode(), received.encode()):
        raise AuthError("invalid_init_data")
    try:
        signed_at = datetime.fromtimestamp(int(fields["auth_date"]), UTC)
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError, OverflowError, OSError) as error:
        raise AuthError("invalid_init_data") from error
    if now - signed_at > MAX_AGE or signed_at - now > MAX_CLOCK_SKEW:
        raise AuthError("expired_init_data")
    return TelegramUser(user_id, _text(user.get("first_name")), _text(user.get("language_code")))
