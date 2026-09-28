from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from scripts.import_v1 import TABLES, Report, main

from assistant.core.db import create_engine
from assistant.core.models import Base

V1_SCHEMA = """
CREATE TABLE users (user_id INTEGER PRIMARY KEY, city TEXT, lat REAL, lon REAL, timezone TEXT,
                    morning_time TEXT, morning_enabled INTEGER, last_morning_date TEXT);
CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT,
                    created_at TEXT);
CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT,
                        remind_at TEXT, sent INTEGER DEFAULT 0);
CREATE TABLE habits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT,
                     created_at TEXT);
CREATE TABLE habit_marks (habit_id INTEGER, day TEXT, done INTEGER, PRIMARY KEY (habit_id, day));
"""


def make_v1(path: Path) -> Path:
    db = sqlite3.connect(path)
    db.executescript(V1_SCHEMA)
    db.executemany(
        "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (111, "Москва", 55.75, 37.62, "Europe/Moscow", "08:00", 1, "2026-09-27"),
            (222, "Владивосток", 43.12, 131.89, "Asia/Vladivostok", "07:30", 0, ""),
            (333, "Атлантида", 0.0, 0.0, "Mars/Olympus", "8:5", 1, ""),
        ],
    )
    db.executemany(
        "INSERT INTO notes VALUES (?, ?, ?, ?)",
        [(1, 111, "купить хлеб", "2026-09-20 10:15"), (2, 999, "чужая", "2026-09-20 10:15")],
    )
    db.executemany(
        "INSERT INTO reminders VALUES (?, ?, ?, ?, ?)",
        [
            (1, 111, "позвонить", "2026-09-25 18:30", 1),
            (2, 222, "встреча", "2026-09-30 09:00", 0),
            (3, 111, "сломанная дата", "завтра", 0),
        ],
    )
    db.executemany(
        "INSERT INTO habits VALUES (?, ?, ?, ?)",
        [(1, 111, "Спорт", "2026-09-19"), (2, 222, "Чтение", "2026-09-26")],
    )
    db.executemany(
        "INSERT INTO habit_marks VALUES (?, ?, ?)",
        [(1, "2026-09-19", 1), (1, "2026-09-20", 0), (5, "2026-09-20", 1)],
    )
    db.commit()
    db.close()
    return path


def make_v2(path: Path) -> Path:
    async def create() -> None:
        engine = create_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create())
    return path


def rows(path: Path, sql: str) -> list[tuple[object, ...]]:
    db = sqlite3.connect(path)
    try:
        return db.execute(sql).fetchall()
    finally:
        db.close()


def test_imports_everything_with_utc_times(tmp_path: Path, capsys) -> None:
    old, new = make_v1(tmp_path / "bot.db"), make_v2(tmp_path / "v2.db")
    assert main([str(old), str(new)]) == 0
    out = capsys.readouterr().out
    assert out.rstrip().endswith("OK") and "Mars/Olympus" in out
    assert rows(
        new,
        "SELECT id, timezone, morning_enabled, morning_time, last_morning_date, "
        "language, tg_language, bot_blocked FROM users ORDER BY id",
    ) == [
        (111, "Europe/Moscow", 1, "08:00", "2026-09-27", None, "ru", 0),
        (222, "Asia/Vladivostok", 0, "07:30", None, None, "ru", 0),
        (333, "Europe/Moscow", 1, "08:05", None, None, "ru", 0),
    ]
    assert rows(new, "SELECT id, user_id, text, created_at FROM notes") == [
        (1, 111, "купить хлеб", "2026-09-20 07:15:00.000000")
    ]
    assert rows(
        new,
        "SELECT id, status, due_at, next_attempt_at, sent_at, attempts FROM reminders ORDER BY id",
    ) == [
        (
            1,
            "sent",
            "2026-09-25 15:30:00.000000",
            "2026-09-25 15:30:00.000000",
            "2026-09-25 15:30:00.000000",
            0,
        ),
        (2, "pending", "2026-09-29 23:00:00.000000", "2026-09-29 23:00:00.000000", None, 0),
    ]
    assert rows(new, "SELECT id, user_id, name, created_on FROM habits ORDER BY id") == [
        (1, 111, "Спорт", "2026-09-19"),
        (2, 222, "Чтение", "2026-09-26"),
    ]
    assert rows(new, "SELECT habit_id, day, done FROM habit_marks ORDER BY day") == [
        (1, "2026-09-19", 1),
        (1, "2026-09-20", 0),
    ]


def test_refuses_a_filled_database_unless_forced(tmp_path: Path, capsys) -> None:
    old, new = make_v1(tmp_path / "bot.db"), make_v2(tmp_path / "v2.db")
    assert main([str(old), str(new)]) == 0
    assert main([str(old), str(new)]) == 2
    assert "--force" in capsys.readouterr().err
    assert main([str(old), str(new), "--force"]) == 0
    assert rows(new, "SELECT count(*) FROM users") == [(3,)]
    assert rows(new, "SELECT count(*) FROM habit_marks") == [(2,)]


def test_refuses_an_unmigrated_database(tmp_path: Path, capsys) -> None:
    old = make_v1(tmp_path / "bot.db")
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert main([str(old), str(empty)]) == 2
    assert "alembic upgrade head" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.db"), str(empty)]) == 2


def test_report_detects_a_mismatch() -> None:
    counts = dict.fromkeys(TABLES, 1)
    report = Report(before=counts, after={**counts, "notes": 0})
    assert not report.ok and report.render().endswith("MISMATCH")
    assert Report(before=counts, after={**counts, "notes": 0}, skipped={"notes": 1}).ok
