"""repeating reminders, snoozed copies, write access

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

import assistant.core.models

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep AUTOINCREMENT when the table is rebuilt: ids of deleted reminders must never come back.
REMINDERS = {"table_kwargs": {"sqlite_autoincrement": True}}


@contextmanager
def _keep_reminders_sequence() -> Iterator[None]:
    """A batch rebuild of `reminders` resets its AUTOINCREMENT counter to max(id): a `seq`
    above that (left behind by rows since deleted) would be forgotten and their ids handed out
    again — an old inline button (which carries an id) could then act on a different, newer
    reminder. Restore the counter around the rebuild."""
    bind = op.get_bind()
    old = bind.execute(sa.text("SELECT seq FROM sqlite_sequence WHERE name = 'reminders'")).scalar()
    yield
    if old is not None:
        bind.execute(sa.text("DELETE FROM sqlite_sequence WHERE name = 'reminders'"))
        bind.execute(
            sa.text(
                "INSERT INTO sqlite_sequence (name, seq) "
                "VALUES ('reminders', max(:old, (SELECT coalesce(max(id), 0) FROM reminders)))"
            ),
            {"old": old},
        )


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("can_write", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # Everyone who exists already came through the bot, so the bot may write to them.
    op.execute("UPDATE users SET can_write = 1")
    with _keep_reminders_sequence():
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
    with _keep_reminders_sequence():
        # v2.1's status type does not know "done"; a row like that would crash it on read.
        op.execute("UPDATE reminders SET status = 'sent' WHERE status = 'done'")
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
