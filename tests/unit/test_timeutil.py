from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from assistant.core import timeutil


def test_local_to_utc_regular_moscow() -> None:
    assert timeutil.local_to_utc(datetime(2026, 9, 28, 18, 30), "Europe/Moscow") == datetime(
        2026, 9, 28, 15, 30, tzinfo=UTC
    )


def test_local_to_utc_dst_gap_moves_forward() -> None:
    # 02:30 does not exist in Berlin on 2027-03-28; it becomes 03:30 local = 01:30 UTC
    result = timeutil.local_to_utc(datetime(2027, 3, 28, 2, 30), "Europe/Berlin")
    assert result == datetime(2027, 3, 28, 1, 30, tzinfo=UTC)
    assert timeutil.to_local(result, "Europe/Berlin").hour == 3


def test_local_to_utc_ambiguous_takes_first_occurrence() -> None:
    result = timeutil.local_to_utc(datetime(2027, 10, 31, 2, 30), "Europe/Berlin")
    assert result == datetime(2027, 10, 31, 0, 30, tzinfo=UTC)


def test_local_to_utc_ambiguous_with_fold_takes_the_second_occurrence() -> None:
    result = timeutil.local_to_utc(datetime(2027, 10, 31, 2, 30, fold=1), "Europe/Berlin")
    assert result == datetime(2027, 10, 31, 1, 30, tzinfo=UTC)


def test_local_to_utc_rejects_aware() -> None:
    with pytest.raises(ValueError):
        timeutil.local_to_utc(datetime(2026, 1, 1, tzinfo=UTC), "Europe/Moscow")


def test_local_today_differs_by_zone() -> None:
    now = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    assert timeutil.local_today("Europe/Moscow", now) == date(2026, 9, 28)
    assert timeutil.local_today("Asia/Vladivostok", now) == date(2026, 9, 29)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 28, 7, 59), None),
        (datetime(2026, 9, 28, 8, 0), date(2026, 9, 28)),
        (datetime(2026, 9, 28, 8, 59), date(2026, 9, 28)),
        (datetime(2026, 9, 28, 9, 0), None),
    ],
)
def test_digest_window(now: datetime, expected: date | None) -> None:
    assert timeutil.digest_window_date(now, "08:00") == expected


def test_digest_window_crossing_midnight_belongs_to_start_day() -> None:
    assert timeutil.digest_window_date(datetime(2026, 9, 28, 23, 45), "23:30") == date(2026, 9, 28)
    assert timeutil.digest_window_date(datetime(2026, 9, 29, 0, 15), "23:30") == date(2026, 9, 28)
    assert timeutil.digest_window_date(datetime(2026, 9, 29, 0, 31), "23:30") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7:30", "07:30"),
        ("07:30", "07:30"),
        ("12:5", "12:05"),
        (" 23:59 ", "23:59"),
        ("24:00", None),
        ("25:70", None),
        ("abc", None),
        ("", None),
        ("7.30", None),
    ],
)
def test_parse_hhmm(text: str, expected: str | None) -> None:
    assert timeutil.parse_hhmm(text) == expected


def test_is_valid_timezone() -> None:
    assert timeutil.is_valid_timezone("Asia/Vladivostok")
    assert not timeutil.is_valid_timezone("Mars/Olympus")
    # Folders of the zone database: opening one fails with an OSError, not a lookup error.
    assert not timeutil.is_valid_timezone("Europe")
    assert not timeutil.is_valid_timezone("America/Argentina")


def test_supported_years_are_one_core_range() -> None:
    # The API refuses dates outside these years before any date arithmetic can overflow.
    years = timeutil.SUPPORTED_YEARS
    assert (years[0], years[-1]) == (2000, 2100)
    assert 1999 not in years and 2101 not in years
