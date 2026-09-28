from __future__ import annotations

import os

# Settings require a token; tests never talk to Telegram.
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-UNIT-TESTS-ONLY")
