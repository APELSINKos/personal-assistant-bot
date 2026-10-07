"""weather and notes: pinned notes, checklist items, extra weather cities

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-05 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

import assistant.core.models

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


@contextmanager
def _keep_sequences(*tables: str) -> Iterator[None]:
    """Dropping a table deletes its AUTOINCREMENT counter from `sqlite_sequence`; put the rows
    back. After an upgrade to 2.6 again the new tables pick their counters up, so the ids of
    items and cities deleted before the downgrade are never handed out again: an old inline
    button (which carries an id) can never act on a newer item or city."""
    bind = op.get_bind()
    kept = {
        table: bind.execute(
            sa.text("SELECT seq FROM sqlite_sequence WHERE name = :name"), {"name": table}
        ).scalar()
        for table in tables
    }
    yield
    for table, seq in kept.items():
        if seq is not None:
            bind.execute(
                sa.text("INSERT INTO sqlite_sequence (name, seq) VALUES (:name, :seq)"),
                {"name": table, "seq": seq},
            )


def upgrade() -> None:
    # A nullable column is a plain ALTER TABLE ADD COLUMN in SQLite: no rebuild of `notes`.
    op.add_column(
        "notes", sa.Column("pinned_at", assistant.core.models.UTCDateTime(), nullable=True)
    )
    op.create_table(
        "note_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=100), nullable=False),
        sa.Column("done", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["notes.id"],
            name=op.f("fk_note_items_note_id_notes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_items")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("note_items", schema=None) as batch_op:
        batch_op.create_index("ix_note_items_note", ["note_id", "id"], unique=False)
    op.create_table(
        "weather_cities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("admin", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("geo_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.CheckConstraint("lat BETWEEN -90 AND 90", name=op.f("ck_weather_cities_lat_range")),
        sa.CheckConstraint("lon BETWEEN -180 AND 180", name=op.f("ck_weather_cities_lon_range")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_weather_cities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weather_cities")),
        sa.UniqueConstraint("user_id", "geo_id", name=op.f("uq_weather_cities_user_id_geo_id")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("weather_cities", schema=None) as batch_op:
        batch_op.create_index("ix_weather_cities_user", ["user_id", "id"], unique=False)


def downgrade() -> None:
    with _keep_sequences("note_items", "weather_cities"):
        with op.batch_alter_table("weather_cities", schema=None) as batch_op:
            batch_op.drop_index("ix_weather_cities_user")
        op.drop_table("weather_cities")
        with op.batch_alter_table("note_items", schema=None) as batch_op:
            batch_op.drop_index("ix_note_items_note")
        op.drop_table("note_items")
    # SQLite's own DROP COLUMN (3.35+; the server and CI have 3.45), not a batch rebuild: the
    # table, and with it its AUTOINCREMENT, its index and its counter, stays as it is.
    op.execute("ALTER TABLE notes DROP COLUMN pinned_at")
