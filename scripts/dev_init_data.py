"""Print a signed Telegram initData string to open the Mini App in an ordinary browser.

Usage:  uv run python scripts/dev_init_data.py --user-id 123456 [--first-name Alex] [--lang ru]

The token comes from BOT_TOKEN (environment or .env) — use a test bot's token, not production's.
Put the printed line into webapp/.env.local as VITE_DEV_INIT_DATA=<line>; it is valid for 24 hours.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from assistant.api.auth import sign_init_data
from assistant.core.config import get_settings
from assistant.core.timeutil import utcnow


def build(user_id: int, first_name: str, lang: str, token: str, now: datetime) -> str:
    user = {"id": user_id, "first_name": first_name, "language_code": lang}
    fields = {
        "auth_date": str(int(now.timestamp())),
        "query_id": "dev",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    return sign_init_data(fields, token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--first-name", default="Dev")
    parser.add_argument("--lang", default="ru", choices=("ru", "en"))
    args = parser.parse_args(argv)
    token = get_settings().bot_token.get_secret_value()
    print(build(args.user_id, args.first_name, args.lang, token, utcnow()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
