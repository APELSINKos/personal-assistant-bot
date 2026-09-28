"""One-time import of the v1 database (bot.db) into the v2 schema.

Usage:  uv run python scripts/import_v1.py OLD_BOT_DB NEW_ASSISTANT_DB [--force]

The new database must already be migrated (`alembic upgrade head`). The script refuses to
touch a database that already has users unless --force is given (then it is emptied first).
Exit codes: 0 — every row imported, 1 — row counts differ, 2 — refused to run.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.models import FsmState, Habit, HabitMark, Note, Reminder, ReminderStatus, User
from assistant.core.timeutil import is_valid_timezone, local_to_utc, parse_hhmm

TABLES = ("users", "notes", "reminders", "habits", "habit_marks")
MODELS: dict[str, type[Any]] = {
    "users": User,
    "notes": Note,
    "reminders": Reminder,
    "habits": Habit,
    "habit_marks": HabitMark,
}
FALLBACK_TZ = "Europe/Moscow"
V1_MINUTE = "%Y-%m-%d %H:%M"
QUERIES = {
    "users": "SELECT user_id, city, lat, lon, timezone, morning_time, morning_enabled, "
    "last_morning_date FROM users ORDER BY user_id",
    "notes": "SELECT id, user_id, text, created_at FROM notes ORDER BY id",
    "reminders": "SELECT id, user_id, text, remind_at, sent FROM reminders ORDER BY id",
    "habits": "SELECT id, user_id, name, created_at FROM habits ORDER BY id",
    "habit_marks": "SELECT habit_id, day, done FROM habit_marks ORDER BY habit_id, day",
}


class Refused(Exception):
    pass


@dataclass
class Report:
    before: dict[str, int] = field(default_factory=dict)
    after: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(
            self.before.get(t, 0) - self.skipped.get(t, 0) == self.after.get(t, 0) for t in TABLES
        )

    def skip(self, table: str, reason: str) -> None:
        self.skipped[table] = self.skipped.get(table, 0) + 1
        self.warnings.append(f"skipped {table}: {reason}")

    def render(self) -> str:
        lines = [f"{'table':<12}{'v1':>6}{'v2':>6}{'skipped':>9}"]
        lines += [
            f"{t:<12}{self.before.get(t, 0):>6}{self.after.get(t, 0):>6}{self.skipped.get(t, 0):>9}"
            for t in TABLES
        ]
        lines += self.warnings
        lines.append("OK" if self.ok else "MISMATCH")
        return "\n".join(lines)


def read_v1(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:
        return {table: db.execute(sql).fetchall() for table, sql in QUERIES.items()}


def _users(
    session: AsyncSession, data: Sequence[tuple[Any, ...]], report: Report
) -> dict[int, str]:
    zones: dict[int, str] = {}
    for user_id, city, lat, lon, tz, morning_time, enabled, last_date in data:
        if not tz or not is_valid_timezone(tz):
            report.warnings.append(f"user {user_id}: unknown time zone {tz!r}, using {FALLBACK_TZ}")
            tz = FALLBACK_TZ
        zones[user_id] = tz
        session.add(
            User(
                # v1 was Russian-only; the real Telegram code replaces this on the next message.
                id=user_id,
                first_name=None,
                language=None,
                tg_language="ru",
                city=city or "Москва",
                lat=float(lat or 0),
                lon=float(lon or 0),
                timezone=tz,
                morning_enabled=bool(enabled),
                morning_time=parse_hhmm(morning_time or "") or "08:00",
                last_morning_date=date.fromisoformat(last_date) if last_date else None,
                bot_blocked=False,
            )
        )
    return zones


def _notes(
    session: AsyncSession, data: Sequence[tuple[Any, ...]], zones: dict[int, str], report: Report
) -> None:
    for note_id, user_id, text, created_at in data:
        if user_id not in zones:
            report.skip("notes", f"note {note_id} belongs to unknown user {user_id}")
            continue
        try:
            created = local_to_utc(datetime.strptime(created_at, V1_MINUTE), zones[user_id])
        except (TypeError, ValueError):
            report.skip("notes", f"note {note_id} has a bad date {created_at!r}")
            continue
        session.add(
            Note(id=note_id, user_id=user_id, text=text, created_at=created, updated_at=created)
        )


def _reminders(
    session: AsyncSession, data: Sequence[tuple[Any, ...]], zones: dict[int, str], report: Report
) -> None:
    for reminder_id, user_id, text, remind_at, sent in data:
        if user_id not in zones:
            report.skip("reminders", f"reminder {reminder_id} belongs to unknown user {user_id}")
            continue
        try:
            due = local_to_utc(datetime.strptime(remind_at, V1_MINUTE), zones[user_id])
        except (TypeError, ValueError):
            report.skip("reminders", f"reminder {reminder_id} has a bad date {remind_at!r}")
            continue
        session.add(
            Reminder(
                id=reminder_id,
                user_id=user_id,
                text=text,
                due_at=due,
                next_attempt_at=due,
                status=ReminderStatus.SENT if sent else ReminderStatus.PENDING,
                attempts=0,
                sent_at=due if sent else None,
            )
        )


def _habits(
    session: AsyncSession, data: Sequence[tuple[Any, ...]], zones: dict[int, str], report: Report
) -> set[int]:
    imported: set[int] = set()
    for habit_id, user_id, name, created_at in data:
        if user_id not in zones:
            report.skip("habits", f"habit {habit_id} belongs to unknown user {user_id}")
            continue
        try:
            created_on = date.fromisoformat(created_at)
        except (TypeError, ValueError):
            report.skip("habits", f"habit {habit_id} has a bad date {created_at!r}")
            continue
        session.add(
            Habit(
                id=habit_id,
                user_id=user_id,
                name=name,
                created_on=created_on,
                created_at=local_to_utc(datetime.combine(created_on, time()), zones[user_id]),
            )
        )
        imported.add(habit_id)
    return imported


def _marks(
    session: AsyncSession, data: Sequence[tuple[Any, ...]], habit_ids: set[int], report: Report
) -> None:
    for habit_id, day, done in data:
        if habit_id not in habit_ids:
            report.skip("habit_marks", f"mark of unknown habit {habit_id}")
            continue
        try:
            session.add(HabitMark(habit_id=habit_id, day=date.fromisoformat(day), done=bool(done)))
        except (TypeError, ValueError):
            report.skip("habit_marks", f"mark of habit {habit_id} has a bad day {day!r}")


async def import_v1(old: Path, new: Path, *, force: bool = False) -> Report:
    data = read_v1(old)
    report = Report(before={table: len(data[table]) for table in TABLES})
    engine = create_engine(f"sqlite+aiosqlite:///{new.as_posix()}")
    try:
        async with make_sessionmaker(engine)() as session:
            try:
                existing = await session.scalar(select(func.count()).select_from(User))
            except OperationalError as error:
                message = "the new database has no schema; run `alembic upgrade head` first"
                raise Refused(message) from error
            if existing and not force:
                raise Refused(
                    f"the new database already has {existing} users; "
                    "use --force to replace everything in it"
                )
            for model in (HabitMark, Habit, Reminder, Note, FsmState, User):
                await session.execute(delete(model))
            zones = _users(session, data["users"], report)
            # Models expose plain foreign-key columns without ORM relationship(), so the unit of
            # work will not order cross-table inserts for us; flush parents before children.
            await session.flush()
            _notes(session, data["notes"], zones, report)
            _reminders(session, data["reminders"], zones, report)
            habit_ids = _habits(session, data["habits"], zones, report)
            await session.flush()
            _marks(session, data["habit_marks"], habit_ids, report)
            await session.commit()
            for table, model in MODELS.items():
                report.after[table] = int(
                    await session.scalar(select(func.count()).select_from(model)) or 0
                )
    finally:
        await engine.dispose()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import the v1 bot.db into the v2 database.")
    parser.add_argument("old", type=Path, help="path to the v1 bot.db")
    parser.add_argument("new", type=Path, help="path to the migrated v2 database")
    parser.add_argument("--force", action="store_true", help="empty the v2 database first")
    args = parser.parse_args(argv)
    for path in (args.old, args.new):
        if not path.is_file():
            print(f"refused: {path} does not exist", file=sys.stderr)
            return 2
    try:
        report = asyncio.run(import_v1(args.old, args.new, force=args.force))
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
