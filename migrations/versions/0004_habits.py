"""habits: emoji, colour and weekly goal; share cards

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

import assistant.core.models

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HABITS = {"table_kwargs": {"sqlite_autoincrement": True}}


@contextmanager
def _keep_habits_sequence() -> Iterator[None]:
    """Dropping columns rebuilds `habits`, and a rebuild resets its AUTOINCREMENT counter to
    max(id): the ids of habits deleted since would be handed out again, and an old inline
    button (which carries an id) could then act on a newer habit. Restore the counter."""
    bind = op.get_bind()
    old = bind.execute(sa.text("SELECT seq FROM sqlite_sequence WHERE name = 'habits'")).scalar()
    yield
    if old is not None:
        bind.execute(sa.text("DELETE FROM sqlite_sequence WHERE name = 'habits'"))
        bind.execute(
            sa.text(
                "INSERT INTO sqlite_sequence (name, seq) "
                "VALUES ('habits', max(:old, (SELECT coalesce(max(id), 0) FROM habits)))"
            ),
            {"old": old},
        )


def upgrade() -> None:
    # Adding columns is a plain ALTER TABLE ADD COLUMN in SQLite: no rebuild of `habits`.
    with op.batch_alter_table("habits", schema=None, **HABITS) as batch_op:
        batch_op.add_column(
            sa.Column("emoji", sa.String(length=16), nullable=False, server_default="🎯")
        )
        batch_op.add_column(
            sa.Column("color", sa.String(length=16), nullable=False, server_default="mint")
        )
        batch_op.add_column(
            sa.Column("weekly_goal", sa.SmallInteger(), nullable=False, server_default="7")
        )
    op.create_table(
        "share_cards",
        sa.Column("token", sa.String(length=43), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.Column("expires_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["habit_id"],
            ["habits.id"],
            name=op.f("fk_share_cards_habit_id_habits"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_share_cards_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_share_cards")),
    )
    with op.batch_alter_table("share_cards", schema=None) as batch_op:
        batch_op.create_index("ix_share_cards_expires", ["expires_at"], unique=False)
        batch_op.create_index("ix_share_cards_user", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("share_cards", schema=None) as batch_op:
        batch_op.drop_index("ix_share_cards_user")
        batch_op.drop_index("ix_share_cards_expires")
    op.drop_table("share_cards")
    with (
        _keep_habits_sequence(),
        op.batch_alter_table("habits", schema=None, **HABITS) as batch_op,
    ):
        batch_op.drop_column("weekly_goal")
        batch_op.drop_column("color")
        batch_op.drop_column("emoji")
