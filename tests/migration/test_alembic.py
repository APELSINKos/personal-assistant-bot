from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]


def _config(db_path: Path) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    return cfg


def test_upgrade_creates_schema_and_matches_models(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _config(db)
    command.upgrade(cfg, "head")
    tables = {
        row[0]
        for row in sqlite3.connect(db).execute("select name from sqlite_master where type='table'")
    }
    assert {"users", "notes", "reminders", "habits", "habit_marks", "fsm_state"} <= tables
    command.check(cfg)  # raises if models and migrations differ


def test_downgrade_to_base_and_back(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "m.db")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
