from __future__ import annotations

import asyncio
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection

from assistant.core.db import create_engine

ROOT = Path(__file__).resolve().parents[2]
CHILDREN = ("notes", "reminders", "habits", "habit_marks")
STAMP = "2026-09-28 10:00:00.000000"
FILL = f"""
INSERT INTO users (id, city, lat, lon, timezone, morning_enabled, morning_time, bot_blocked,
                   created_at, updated_at)
VALUES (1, 'Москва', 55.75, 37.62, 'Europe/Moscow', 1, '08:00', 0, '{STAMP}', '{STAMP}');
INSERT INTO notes (user_id, text, created_at, updated_at) VALUES (1, 'n', '{STAMP}', '{STAMP}');
INSERT INTO reminders (user_id, text, due_at, status, attempts, next_attempt_at, created_at)
VALUES (1, 'r', '{STAMP}', 'pending', 0, '{STAMP}', '{STAMP}');
INSERT INTO habits (user_id, name, created_on, created_at) VALUES (1, 'h', '2026-09-28', '{STAMP}');
INSERT INTO habit_marks (habit_id, day, done) VALUES (1, '2026-09-28', 1);
"""
REVISION = """
from __future__ import annotations

from alembic import op

revision = "test_extra"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
{body}


def downgrade() -> None:
    pass
"""
REBUILD_USERS = """\
    if op.get_bind().exec_driver_sql("PRAGMA foreign_keys").scalar() != 0:
        raise RuntimeError("foreign keys are on while migrating")
    with op.batch_alter_table("users", recreate="always"):
        pass"""
ORPHAN_NOTE = f"""\
    op.execute(
        "INSERT INTO notes (user_id, text, created_at, updated_at) "
        "VALUES (42, 'orphan', '{STAMP}', '{STAMP}')"
    )"""


def _config(db_path: Path, scripts: Path = ROOT / "migrations") -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(scripts))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    return cfg


def _scripts_with(tmp_path: Path, body: str) -> Path:
    """A copy of the real migrations (env.py included) plus one extra revision."""
    scripts = tmp_path / "migrations"
    shutil.copytree(ROOT / "migrations", scripts, ignore=shutil.ignore_patterns("__pycache__"))
    (scripts / "versions" / "test_extra.py").write_text(
        REVISION.format(body=body), encoding="utf-8"
    )
    return scripts


def _fill(db: Path) -> None:
    with closing(sqlite3.connect(db)) as conn:
        conn.executescript(FILL)


def _counts(db: Path) -> dict[str, int]:
    with closing(sqlite3.connect(db)) as conn:
        return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in CHILDREN}


def test_upgrade_creates_schema_and_matches_models(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _config(db)
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(db)) as conn:
        schema = dict(conn.execute("select name, sql from sqlite_master where type='table'"))
    assert {
        "users",
        "notes",
        "reminders",
        "habits",
        "habit_marks",
        "fsm_state",
        "mirea_groups",
        "schedule_sources",
        "lessons",
        "week_labels",
        "lesson_alerts",
        "job_runs",
        "share_cards",
    } <= set(schema)
    # AUTOINCREMENT: ids of deleted rows are never reused. `alembic check` does not compare it
    # and a batch rebuild drops it unless given table_kwargs={"sqlite_autoincrement": True}.
    assert "sqlite_sequence" in schema
    for table in ("notes", "reminders", "habits"):
        assert "AUTOINCREMENT" in schema[table], table
    command.check(cfg)  # raises if models and migrations differ


def test_downgrade_to_base_and_back(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "m.db")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_engine_without_foreign_keys_keeps_children_on_batch_rebuild(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _config(db)
    # Fill against the 0001 shape: 0002 requires reminders.occurrence_at, which this raw
    # insert does not set; the migration itself backfills it when upgrading past 0001.
    command.upgrade(cfg, "0001")
    _fill(db)
    command.upgrade(cfg, "head")

    def rebuild(connection: Connection) -> None:
        operations = Operations(MigrationContext.configure(connection))
        with operations.batch_alter_table("users", recreate="always"):
            pass

    async def run() -> None:
        engine = create_engine(f"sqlite+aiosqlite:///{db.as_posix()}", foreign_keys=False)
        async with engine.begin() as connection:
            await connection.run_sync(rebuild)
        await engine.dispose()

    asyncio.run(run())
    assert _counts(db) == dict.fromkeys(CHILDREN, 1)


def test_migrations_rebuild_a_parent_table_without_losing_children(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _config(db, _scripts_with(tmp_path, REBUILD_USERS))
    command.upgrade(cfg, "0001")
    _fill(db)
    command.upgrade(cfg, "head")
    assert _counts(db) == dict.fromkeys(CHILDREN, 1)


def test_migration_that_leaves_broken_references_fails(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _config(db, _scripts_with(tmp_path, ORPHAN_NOTE))
    with pytest.raises(RuntimeError, match=r"broken foreign keys.*notes"):
        command.upgrade(cfg, "head")


def test_0002_keeps_v2_1_data(tmp_path: Path) -> None:
    db = tmp_path / "v21.db"
    command.upgrade(_config(db), "0001")
    _fill(db)
    command.upgrade(_config(db), "head")
    assert _counts(db) == {t: 1 for t in CHILDREN}
    with closing(sqlite3.connect(db)) as conn:
        row = conn.execute(
            "SELECT repeat, interval_weeks, occurrence_at = due_at, parent_id FROM reminders"
        ).fetchone()
        can_write = conn.execute("SELECT can_write FROM users").fetchone()[0]
        autoincrement = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'reminders'"
        ).fetchone()[0]
    assert row == ("none", 1, 1, None)
    assert can_write == 1  # everyone who existed came through the bot
    assert "AUTOINCREMENT" in autoincrement
    # v2.1's status type does not know "done"; downgrading must translate it to one it does.
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("UPDATE reminders SET status = 'done'")
        conn.commit()
    command.downgrade(_config(db), "0001")
    assert _counts(db) == {t: 1 for t in CHILDREN}
    with closing(sqlite3.connect(db)) as conn:
        status = conn.execute("SELECT status FROM reminders").fetchone()[0]
    assert status == "sent"


def test_0002_preserves_the_id_sequence_through_upgrade_and_downgrade(tmp_path: Path) -> None:
    db = tmp_path / "seq.db"
    cfg = _config(db)
    command.upgrade(cfg, "0001")
    _fill(db)  # one reminder already exists, with id 1

    def insert(conn: sqlite3.Connection, text: str, *, with_occurrence: bool) -> int:
        columns = [
            "user_id",
            "text",
            "due_at",
            "status",
            "attempts",
            "next_attempt_at",
            "created_at",
        ]
        values: list[object] = [1, text, STAMP, "pending", 0, STAMP, STAMP]
        if with_occurrence:
            columns.append("occurrence_at")
            values.append(STAMP)
        placeholders = ", ".join("?" for _ in values)
        conn.execute(
            f"INSERT INTO reminders ({', '.join(columns)}) VALUES ({placeholders})", values
        )
        return int(conn.execute("SELECT id FROM reminders WHERE text = ?", (text,)).fetchone()[0])

    def seq(conn: sqlite3.Connection) -> int:
        return int(
            conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'reminders'").fetchone()[0]
        )

    with closing(sqlite3.connect(db)) as conn:
        gone_id = insert(conn, "gone", with_occurrence=False)
        assert gone_id == 2
        conn.execute("DELETE FROM reminders WHERE id = ?", (gone_id,))
        conn.commit()

    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(db)) as conn:
        assert seq(conn) == 2  # the deleted reminder's id must not come back
        new_id = insert(conn, "new", with_occurrence=True)
        assert new_id == 3  # a fresh id, not the deleted one
        conn.execute("DELETE FROM reminders WHERE id = ?", (new_id,))  # seq outruns max(id) again
        conn.commit()

    command.downgrade(cfg, "0001")
    with closing(sqlite3.connect(db)) as conn:
        assert seq(conn) == 3  # still not reset by the downgrade's own rebuild
        newest_id = insert(conn, "newest", with_occurrence=False)
        assert newest_id == 4


def test_0003_keeps_existing_data_and_downgrades(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    # Filled in the 0001 shape (FILL's raw inserts predate 0002's columns), then brought up
    # through 0002 and 0003: every existing row must survive both.
    command.upgrade(_config(db), "0001")
    _fill(db)
    command.upgrade(_config(db), "head")
    assert _counts(db) == {t: 1 for t in CHILDREN}
    with closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "INSERT INTO schedule_sources (user_id, kind, fetched_at, next_refresh_at, created_at) "
            f"VALUES (1, 'file', '{STAMP}', '{STAMP}', '{STAMP}')"
        )
        conn.execute(
            "INSERT INTO lessons (user_id, uid, starts_at, ends_at, title) "
            f"VALUES (1, 'u', '{STAMP}', '{STAMP}', 'x')"
        )
        conn.commit()
    command.downgrade(_config(db), "0002")
    assert _counts(db) == {t: 1 for t in CHILDREN}
    with closing(sqlite3.connect(db)) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert not tables & {"schedule_sources", "lessons", "mirea_groups", "job_runs"}


def test_0004_gives_habits_the_default_look_and_downgrades_without_reusing_ids(
    tmp_path: Path,
) -> None:
    db = tmp_path / "old.db"
    cfg = _config(db)
    command.upgrade(cfg, "0001")
    _fill(db)
    command.upgrade(cfg, "0003")
    with closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "INSERT INTO habits (user_id, name, created_on, created_at) "
            f"VALUES (1, 'gone', '2026-09-28', '{STAMP}')"
        )
        conn.execute("DELETE FROM habits WHERE name = 'gone'")  # sqlite_sequence 2, max(id) 1
        conn.commit()
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(db)) as conn:
        looks = conn.execute("SELECT emoji, color, weekly_goal FROM habits").fetchall()
        conn.execute(
            "INSERT INTO share_cards (token, user_id, habit_id, image, created_at, expires_at) "
            f"VALUES ('{'t' * 43}', 1, 1, x'ffd8', '{STAMP}', '{STAMP}')"
        )
        conn.commit()
    assert looks == [("🎯", "mint", 7)]
    # The CHECK constraint prevents invalid weekly_goal values.
    with closing(sqlite3.connect(db)) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE habits SET weekly_goal = 0")
        conn.commit()
    command.downgrade(cfg, "0003")
    assert _counts(db) == {t: 1 for t in CHILDREN}
    with closing(sqlite3.connect(db)) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(habits)")}
        seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'habits'").fetchone()[0]
    assert "share_cards" not in tables
    assert not columns & {"emoji", "color", "weekly_goal"}
    assert seq == 2  # the deleted habit's id is not handed out again
