"""income and the «Зв'язок» default category

Revision ID: 0003
Revises: 0002
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CONNECTIVITY = "Зв'язок"
CONNECTIVITY_NORMALIZED = "зв'язок"  # normalize_category_name(CONNECTIVITY)

categories = sa.table(
    "categories",
    sa.column("household_id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("name_normalized", sa.String),
    sa.column("is_custom", sa.Boolean),
    sa.column("created_at", sa.DateTime),
)


def upgrade() -> None:
    op.create_table(
        "incomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_incomes_lookup", "incomes", ["household_id", "effective_from"])

    # Only households that already have categories: one with none is seeded
    # later by ensure_default_categories, which skips any household that has
    # at least one category.
    connection = op.get_bind()
    with_categories = set(
        connection.execute(sa.select(categories.c.household_id).distinct()).scalars()
    )
    with_connectivity = set(
        connection.execute(
            sa.select(categories.c.household_id).where(
                categories.c.name_normalized == CONNECTIVITY_NORMALIZED
            )
        ).scalars()
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    for household_id in sorted(with_categories - with_connectivity):
        connection.execute(
            categories.insert().values(
                household_id=household_id,
                name=CONNECTIVITY,
                name_normalized=CONNECTIVITY_NORMALIZED,
                is_custom=False,
                created_at=now,
            )
        )


def downgrade() -> None:
    # «Зв'язок» stays: expenses may already point at it.
    op.drop_index("ix_incomes_lookup", table_name="incomes")
    op.drop_table("incomes")
