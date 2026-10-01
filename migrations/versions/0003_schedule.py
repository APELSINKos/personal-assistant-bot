"""schedule: MIREA group directory, schedule sources, lessons, week labels, alerts, job runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import assistant.core.models

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("finished_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.Column("info", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_job_runs")),
    )
    op.create_table(
        "mirea_groups",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("name_key", sa.String(length=40), nullable=False),
        sa.Column("semester_end", sa.Date(), nullable=False),
        sa.Column("seen_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mirea_groups")),
    )
    with op.batch_alter_table("mirea_groups", schema=None) as batch_op:
        batch_op.create_index("ix_mirea_groups_name_key", ["name_key"], unique=False)

    op.create_table(
        "lesson_alerts",
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("uid", sa.String(length=255), nullable=False),
        sa.Column("starts_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.Column("sent_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_lesson_alerts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "uid", "starts_at", name=op.f("pk_lesson_alerts")),
    )
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("uid", sa.String(length=255), nullable=False),
        sa.Column("starts_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.Column("ends_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=True),
        sa.Column("room", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_lessons_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
    )
    with op.batch_alter_table("lessons", schema=None) as batch_op:
        batch_op.create_index("ix_lessons_user", ["user_id", "starts_at"], unique=False)

    op.create_table(
        "schedule_sources",
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("mirea_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("body", sa.LargeBinary(), nullable=True),
        sa.Column("fetched_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.Column("ok_at", assistant.core.models.UTCDateTime(), nullable=True),
        sa.Column("error", sa.String(length=32), nullable=True),
        sa.Column("next_refresh_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.Column("lesson_reminder_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_schedule_sources_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_schedule_sources")),
    )
    op.create_table(
        "week_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_week_labels_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_week_labels")),
    )
    with op.batch_alter_table("week_labels", schema=None) as batch_op:
        batch_op.create_index("ix_week_labels_user", ["user_id", "start_date"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("week_labels", schema=None) as batch_op:
        batch_op.drop_index("ix_week_labels_user")
    op.drop_table("week_labels")
    op.drop_table("schedule_sources")
    with op.batch_alter_table("lessons", schema=None) as batch_op:
        batch_op.drop_index("ix_lessons_user")
    op.drop_table("lessons")
    op.drop_table("lesson_alerts")
    with op.batch_alter_table("mirea_groups", schema=None) as batch_op:
        batch_op.drop_index("ix_mirea_groups_name_key")
    op.drop_table("mirea_groups")
    op.drop_table("job_runs")
