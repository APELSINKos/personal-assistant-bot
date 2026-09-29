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
down_revision = "0002"
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
    assert {"users", "notes", "reminders", "habits", "habit_marks", "fsm_state"} <= set(schema)
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
    command.downgrade(_config(db), "0001")
    assert _counts(db) == {t: 1 for t in CHILDREN}
