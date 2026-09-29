from __future__ import annotations

from assistant.api.ratelimit import RateLimiter


def test_limit_answers_the_exact_wait_and_frees_up_after_the_window() -> None:
    now = [1000.0]
    limiter = RateLimiter(3, window=60.0, clock=lambda: now[0])
    for moment in (1000.0, 1010.0, 1020.0):
        now[0] = moment
        assert limiter.check(1) is None
    now[0] = 1030.0
    assert limiter.check(1) == 30.0  # the oldest request leaves the window at 1060
    assert limiter.check(2) is None  # every user has a window of their own
    now[0] = 1059.5
    assert limiter.check(1) == 0.5
    now[0] = 1060.0
    assert limiter.check(1) is None
    assert limiter.check(1) == 10.0  # now the request made at 1010 is the oldest
