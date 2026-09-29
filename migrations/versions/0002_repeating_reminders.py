"""repeating reminders, snoozed copies, write access

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import assistant.core.models

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep AUTOINCREMENT when the table is rebuilt: ids of deleted reminders must never come back.
REMINDERS = {"table_kwargs": {"sqlite_autoincrement": True}}


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("can_write", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # Everyone who exists already came through the bot, so the bot may write to them.
    op.execute("UPDATE users SET can_write = 1")
    with op.batch_alter_table("reminders", schema=None, **REMINDERS) as batch_op:
        batch_op.add_column(
            sa.Column("repeat", sa.String(length=8), nullable=False, server_default="none")
        )
        batch_op.add_column(sa.Column("time_local", sa.String(length=5), nullable=True))
        batch_op.add_column(sa.Column("anchor_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("weekdays", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("interval_weeks", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("month_day", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("occurrence_at", assistant.core.models.UTCDateTime(), nullable=True)
        )
        batch_op.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_reminders_parent_id_reminders"),
            "reminders",
            ["parent_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute("UPDATE reminders SET occurrence_at = due_at")
    with op.batch_alter_table("reminders", schema=None, **REMINDERS) as batch_op:
        batch_op.alter_column(
            "occurrence_at", existing_type=assistant.core.models.UTCDateTime(), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("reminders", schema=None, **REMINDERS) as batch_op:
        batch_op.drop_constraint("fk_reminders_parent_id_reminders", type_="foreignkey")
        for column in (
            "parent_id",
            "occurrence_at",
            "month_day",
            "interval_weeks",
            "weekdays",
            "anchor_date",
            "time_local",
            "repeat",
        ):
            batch_op.drop_column(column)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("can_write")
