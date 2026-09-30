"""limits and one-time expenses

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "limits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("period_type", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_limits_lookup",
        "limits",
        ["household_id", "period_type", "category_id", "effective_from"],
    )
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(
            sa.Column("is_one_time", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("is_one_time")
    op.drop_index("ix_limits_lookup", table_name="limits")
    op.drop_table("limits")
