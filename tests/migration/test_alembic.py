from __future__ import annotations

import asyncio
import shutil
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

from assistant.core.db import create_engine
from assistant.core.models import Base

ROOT = Path(__file__).resolve().parents[2]
# Every table the models give AUTOINCREMENT: ids of its deleted rows must never come back.
AUTOINCREMENT = tuple(
    table.name
    for table in Base.metadata.sorted_tables
    if table.dialect_options["sqlite"]["autoincrement"]
)
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
# The tables of 2.6 exist from 0006 on, so they are filled after upgrade(cfg, "0006") and never
# in FILL: the tests of 0002–0005 take the database down to 0001–0004, where they are missing.
CHILDREN_26 = ("note_items", "weather_cities")
FILL_26 = f"""
INSERT INTO note_items (note_id, text, created_at) VALUES (1, 'i', '{STAMP}');
INSERT INTO weather_cities (user_id, name, lat, lon, timezone, geo_id, created_at)
VALUES (1, 'Тула', 54.19, 37.62, 'Europe/Moscow', 480562, '{STAMP}');
"""
REVISION = """
from __future__ import annotations

from alembic import op

revision = "test_extra"
down_revision = "0007"
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


def _fill(db: Path, script: str = FILL) -> None:
    with closing(sqlite3.connect(db)) as conn:
        conn.executescript(script)


def _counts(db: Path, tables: Sequence[str] = CHILDREN) -> dict[str, int]:
    with closing(sqlite3.connect(db)) as conn:
        return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}


def _share_card(conn: sqlite3.Connection, letter: str, habit_id: int | None) -> None:
    """A picture of user 1 under the token of 43 `letter`s; no habit: the week's forecast."""
    conn.execute(
        "INSERT INTO share_cards (token, user_id, habit_id, image, created_at, expires_at) "
        "VALUES (?, 1, ?, x'ffd8', ?, ?)",
        (letter * 43, habit_id, STAMP, STAMP),
    )


def _share_cards_shape(db: Path) -> tuple[set[tuple[str, str, str]], dict[str, list[str]], str]:
    """The foreign keys of `share_cards` (column, table, ON DELETE), its indexes with their
    columns and its SQL: a rebuild of the table must keep them all."""
    with closing(sqlite3.connect(db)) as conn:
        keys = {
            (row[3], row[2], row[6]) for row in conn.execute("PRAGMA foreign_key_list(share_cards)")
        }
        indexes = {
            row[1]: [column[2] for column in conn.execute(f"PRAGMA index_info({row[1]})")]
            for row in conn.execute("PRAGMA index_list(share_cards)").fetchall()
            if row[3] == "c"  # made by CREATE INDEX, not the primary key's own
        }
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'share_cards'").fetchone()[0]
    return keys, indexes, sql


def test_upgrade_creates_schema_and_matches_models(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _config(db)
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(db)) as conn:
        schema = dict(conn.execute("select name, sql from sqlite_master where type='table'"))
    assert set(Base.metadata.tables) <= set(schema)
    # AUTOINCREMENT: ids of deleted rows are never reused. `alembic check` does not compare it
    # and a batch rebuild drops it unless given table_kwargs={"sqlite_autoincrement": True}.
    assert "sqlite_sequence" in schema
    assert {
        "notes",
        "reminders",
        "habits",
        "money_categories",
        "money_entries",
        "note_items",
        "weather_cities",
    } <= set(AUTOINCREMENT)
    for table in AUTOINCREMENT:
        assert "AUTOINCREMENT" in schema[table], table
    command.check(cfg)  # raises if models and migrations differ


def test_every_id_counter_survives_every_upgrade(tmp_path: Path) -> None:
    """A table rebuild resets its AUTOINCREMENT counter to max(id), a drop deletes it: the ids
    of deleted rows would then come back, and an old inline button (which carries an id) could
    act on a newer row. Each table gets a counter above its ids as soon as a revision creates
    it, and every later revision up to head must keep it."""
    db = tmp_path / "m.db"
    cfg = _config(db)
    revisions = [script.revision for script in ScriptDirectory.from_config(cfg).walk_revisions()]
    counters: dict[str, int] = {}
    for revision in reversed(revisions):  # walk_revisions() goes from head down
        command.upgrade(cfg, revision)
        with closing(sqlite3.connect(db)) as conn:
            assert dict(conn.execute("SELECT name, seq FROM sqlite_sequence")) == counters, revision
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
            for table in sorted(tables & set(AUTOINCREMENT) - set(counters)):
                counters[table] = 1000 + len(counters)
                conn.execute(
                    "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
                    (table, counters[table]),
                )
            conn.commit()
    assert set(counters) == set(AUTOINCREMENT)


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
    command.upgrade(cfg, "0006")
    _fill(db, FILL_26)
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
    assert _counts(db, CHILDREN + CHILDREN_26) == dict.fromkeys(CHILDREN + CHILDREN_26, 1)


def test_migrations_rebuild_a_parent_table_without_losing_children(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _config(db, _scripts_with(tmp_path, REBUILD_USERS))
    command.upgrade(cfg, "0001")
    _fill(db)
    command.upgrade(cfg, "0006")
    _fill(db, FILL_26)
    command.upgrade(cfg, "head")
    assert _counts(db, CHILDREN + CHILDREN_26) == dict.fromkeys(CHILDREN + CHILDREN_26, 1)


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


def test_0005_gives_users_roubles_and_downgrades_keeping_their_data(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    cfg = _config(db)
    command.upgrade(cfg, "0001")
    _fill(db)
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(db)) as conn:
        user = conn.execute("SELECT currency, money_budget FROM users").fetchall()
        conn.execute(
            "INSERT INTO money_categories (user_id, kind, preset, emoji, hidden, position, "
            f"created_at) VALUES (1, 'expense', 'cafe', '☕', 0, 1, '{STAMP}')"
        )
        conn.execute(
            "INSERT INTO money_entries (user_id, category_id, amount, note, day, created_at) "
            f"VALUES (1, 1, 25000, 'кофе', '2026-10-03', '{STAMP}')"
        )
        conn.execute("INSERT INTO money_words (user_id, key, category_id) VALUES (1, 'кофе', 1)")
        conn.execute(
            "INSERT INTO money_alerts (user_id, month, category_id, threshold, sent_at) "
            f"VALUES (1, '2026-10', 0, 80, '{STAMP}')"
        )
        conn.commit()
    assert user == [("RUB", None)]
    for statement in (
        "UPDATE users SET currency = 'RUBLE'",
        "UPDATE users SET money_budget = 0",
        "UPDATE money_entries SET amount = 0",
        "UPDATE money_categories SET kind = 'loan'",
        "UPDATE money_categories SET budget = 100, kind = 'income'",
    ):
        with closing(sqlite3.connect(db)) as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement)
            conn.commit()
    command.downgrade(cfg, "0004")
    assert _counts(db) == {t: 1 for t in CHILDREN}
    with closing(sqlite3.connect(db)) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert not tables & {"money_categories", "money_entries", "money_words", "money_alerts"}
    assert not columns & {"currency", "money_budget"}
    assert broken == []
    command.upgrade(cfg, "head")  # and up again


def test_0006_adds_pins_items_and_cities_and_a_round_trip_keeps_their_counters(
    tmp_path: Path,
) -> None:
    db = tmp_path / "old.db"
    cfg = _config(db)
    command.upgrade(cfg, "0001")
    _fill(db)
    command.upgrade(cfg, "0005")
    with closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "INSERT INTO notes (user_id, text, created_at, updated_at) "
            f"VALUES (1, 'gone', '{STAMP}', '{STAMP}')"
        )
        conn.execute("DELETE FROM notes WHERE text = 'gone'")  # sqlite_sequence 2, max(id) 1
        conn.commit()
    command.upgrade(cfg, "0006")
    _fill(db, FILL_26)
    with closing(sqlite3.connect(db)) as conn:
        pins = conn.execute("SELECT pinned_at FROM notes").fetchall()
        items = conn.execute("SELECT id, done FROM note_items").fetchall()
        cities = conn.execute("SELECT id, admin, country, geo_id FROM weather_cities").fetchall()
        # An item and a city deleted: their ids must not come back after a round trip.
        conn.execute(
            f"INSERT INTO note_items (note_id, text, created_at) VALUES (1, 'gone', '{STAMP}')"
        )
        conn.execute("DELETE FROM note_items WHERE text = 'gone'")
        conn.execute(
            "INSERT INTO weather_cities (user_id, name, lat, lon, timezone, created_at) "
            f"VALUES (1, 'gone', 0, 0, 'UTC', '{STAMP}')"
        )
        conn.execute("DELETE FROM weather_cities WHERE name = 'gone'")
        conn.commit()
        counters = dict(conn.execute("SELECT name, seq FROM sqlite_sequence"))
    assert pins == [(None,)]
    assert items == [(1, 0)]  # `done` is 0 when a write does not name it
    assert cities == [(1, None, None, 480562)]
    # Each counter is above max(id) of its table; `notes` kept its own, so adding the column did
    # not rebuild the table.
    kept = {"reminders": 1, "habits": 1, "notes": 2, "note_items": 2, "weather_cities": 2}
    assert counters == kept
    for statement in (
        "UPDATE weather_cities SET lat = 90.5",
        "UPDATE weather_cities SET lat = -90.5",
        "UPDATE weather_cities SET lon = 180.5",
        "UPDATE weather_cities SET lon = -180.5",
        # The same GeoNames city twice for one user.
        "INSERT INTO weather_cities (user_id, name, lat, lon, timezone, geo_id, created_at) "
        "SELECT user_id, name, lat, lon, timezone, geo_id, created_at FROM weather_cities",
    ):
        with closing(sqlite3.connect(db)) as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement)
            conn.commit()

    command.downgrade(cfg, "0005")
    assert _counts(db) == {t: 1 for t in CHILDREN}
    with closing(sqlite3.connect(db)) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(notes)")}
        notes = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'notes'").fetchone()[0]
        counters = dict(conn.execute("SELECT name, seq FROM sqlite_sequence"))
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert not names & {*CHILDREN_26, "ix_note_items_note", "ix_weather_cities_user"}
    assert "pinned_at" not in columns
    # Dropping the column did not rebuild `notes`: its AUTOINCREMENT, index and counter stay.
    # The counters of the dropped tables are kept for the way back to 2.6.
    assert "AUTOINCREMENT" in notes and "ix_notes_user" in names
    assert counters == kept
    assert broken == []

    command.upgrade(cfg, "head")  # and up again: the ids go on from the old counters
    _fill(db, FILL_26)
    with closing(sqlite3.connect(db)) as conn:
        item_ids = [row[0] for row in conn.execute("SELECT id FROM note_items")]
        city_ids = [row[0] for row in conn.execute("SELECT id FROM weather_cities")]
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM users")  # takes the notes, their items and the cities along
        conn.commit()
    assert item_ids == [3] and city_ids == [3]
    assert _counts(db, CHILDREN_26) == dict.fromkeys(CHILDREN_26, 0)


SHARE_CARDS_KEYS = {("habit_id", "habits", "CASCADE"), ("user_id", "users", "CASCADE")}
SHARE_CARDS_INDEXES = {
    "ix_share_cards_user": ["user_id", "created_at"],
    "ix_share_cards_expires": ["expires_at"],
}


def test_0007_keeps_pictures_without_a_habit_and_indexes_snoozed_copies(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    cfg = _config(db)
    command.upgrade(cfg, "0001")
    _fill(db)
    command.upgrade(cfg, "0006")
    _fill(db, FILL_26)
    with closing(sqlite3.connect(db)) as conn:
        _share_card(conn, "h", 1)  # the habit's card, shared in 2.6
        # Every counter above max(id) of its table: a rebuild would bring it down to max(id).
        conn.execute("UPDATE sqlite_sequence SET seq = seq + 1000")
        conn.commit()
        counters = dict(conn.execute("SELECT name, seq FROM sqlite_sequence"))

    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(db)) as conn:
        _share_card(conn, "f", None)  # the week's forecast: a picture of no habit
        conn.commit()
        cards = conn.execute("SELECT token, habit_id FROM share_cards ORDER BY token").fetchall()
        parent = [row[2] for row in conn.execute("PRAGMA index_info(ix_reminders_parent)")]
        kept = dict(conn.execute("SELECT name, seq FROM sqlite_sequence"))
    assert cards == [("f" * 43, None), ("h" * 43, 1)]
    # ON DELETE SET NULL of a snoozed copy's parent_id no longer reads the whole table, and the
    # index came without a rebuild of `reminders`: no counter came down to max(id).
    assert parent == ["parent_id"]
    assert kept == counters
    keys, indexes, sql = _share_cards_shape(db)
    assert (keys, indexes) == (SHARE_CARDS_KEYS, SHARE_CARDS_INDEXES)
    assert "fk_share_cards_habit_id_habits" in sql and "fk_share_cards_user_id_users" in sql

    command.downgrade(cfg, "0006")
    with closing(sqlite3.connect(db)) as conn:
        cards = conn.execute("SELECT token, habit_id FROM share_cards").fetchall()
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        kept = dict(conn.execute("SELECT name, seq FROM sqlite_sequence"))
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert cards == [("h" * 43, 1)]  # only the forecast went: 2.6 knows no picture without a habit
    assert "ix_reminders_parent" not in names
    assert kept == counters
    assert broken == []
    assert _share_cards_shape(db)[:2] == (SHARE_CARDS_KEYS, SHARE_CARDS_INDEXES)
    with closing(sqlite3.connect(db)) as conn, pytest.raises(sqlite3.IntegrityError):
        _share_card(conn, "f", None)

    command.upgrade(cfg, "head")  # and up again
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _share_card(conn, "f", None)
        conn.execute("DELETE FROM habits")  # takes the habit's card along, not the forecast
        left = [row[0] for row in conn.execute("SELECT token FROM share_cards")]
        conn.execute("DELETE FROM users")  # takes the forecast along: the rebuilt table cascades
        conn.commit()
    assert left == ["f" * 43]
    assert _counts(db, ("share_cards",)) == {"share_cards": 0}
