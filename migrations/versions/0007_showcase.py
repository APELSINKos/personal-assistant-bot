"""showcase: shared pictures of no habit (the forecast), an index on reminders.parent_id

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-09 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite cannot drop a column's NOT NULL in place: `share_cards` is rebuilt (at most ten rows
    # a user, without AUTOINCREMENT) with its keys, their ON DELETE CASCADE and its indexes, read
    # from the table itself. A habit's card still goes with its habit.
    with op.batch_alter_table("share_cards", schema=None) as batch_op:
        batch_op.alter_column("habit_id", existing_type=sa.Integer(), nullable=True)
    # ON DELETE SET NULL of a snoozed copy's parent_id read the whole table for every reminder
    # deleted. A plain CREATE INDEX: no rebuild of `reminders`, so its counter stays.
    op.create_index("ix_reminders_parent", "reminders", ["parent_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reminders_parent", table_name="reminders")
    # 2.6 knows no picture without a habit. The forecast's are snapshots, drawn again on request.
    op.execute("DELETE FROM share_cards WHERE habit_id IS NULL")
    with op.batch_alter_table("share_cards", schema=None) as batch_op:
        batch_op.alter_column("habit_id", existing_type=sa.Integer(), nullable=False)
