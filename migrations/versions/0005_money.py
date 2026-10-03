"""money: the user's currency and budget, categories, entries, remembered notes, warnings

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import assistant.core.models

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A column with its own CHECK is a plain ALTER TABLE ADD COLUMN in SQLite: no rebuild of
    # `users`, whose rows every other table refers to.
    op.execute(
        "ALTER TABLE users ADD COLUMN currency VARCHAR(3) NOT NULL DEFAULT 'RUB' "
        "CONSTRAINT ck_users_currency_code CHECK (length(currency) = 3)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN money_budget BIGINT "
        "CONSTRAINT ck_users_money_budget_positive CHECK (money_budget IS NULL OR money_budget > 0)"
    )
    op.create_table(
        "money_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("preset", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=30), nullable=True),
        sa.Column("emoji", sa.String(length=16), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("budget", sa.BigInteger(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.CheckConstraint(
            "budget IS NULL OR (budget > 0 AND kind = 'expense')",
            name=op.f("ck_money_categories_budget"),
        ),
        sa.CheckConstraint("kind IN ('expense', 'income')", name=op.f("ck_money_categories_kind")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_money_categories_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_money_categories")),
        sa.UniqueConstraint("user_id", "preset", name=op.f("uq_money_categories_user_id_preset")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("money_categories", schema=None) as batch_op:
        batch_op.create_index("ix_money_categories_user", ["user_id"], unique=False)
    op.create_table(
        "money_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(length=100), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_money_entries_amount_positive")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["money_categories.id"],
            name=op.f("fk_money_entries_category_id_money_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_money_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_money_entries")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("money_entries", schema=None) as batch_op:
        batch_op.create_index("ix_money_entries_user_day", ["user_id", "day"], unique=False)
    op.create_table(
        "money_words",
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["money_categories.id"],
            name=op.f("fk_money_words_category_id_money_categories"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_money_words_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "key", name=op.f("pk_money_words")),
    )
    op.create_table(
        "money_alerts",
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("category_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("threshold", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("sent_at", assistant.core.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_money_alerts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "month", "category_id", "threshold", name=op.f("pk_money_alerts")
        ),
    )


def downgrade() -> None:
    op.drop_table("money_alerts")
    op.drop_table("money_words")
    with op.batch_alter_table("money_entries", schema=None) as batch_op:
        batch_op.drop_index("ix_money_entries_user_day")
    op.drop_table("money_entries")
    with op.batch_alter_table("money_categories", schema=None) as batch_op:
        batch_op.drop_index("ix_money_categories_user")
    op.drop_table("money_categories")
    # Dropping columns rebuilds `users`; foreign keys are off during migrations, so the rows
    # that refer to users stay.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_users_money_budget_positive"), type_="check")
        batch_op.drop_constraint(op.f("ck_users_currency_code"), type_="check")
        batch_op.drop_column("money_budget")
        batch_op.drop_column("currency")
