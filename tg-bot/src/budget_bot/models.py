"""SQLAlchemy models. All datetimes are UTC-naive (see budget_bot.clock)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from budget_bot.clock import utcnow


class Base(DeclarativeBase):
    pass


class Household(Base):
    __tablename__ = "households"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("telegram_id", name="uq_members_telegram_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    display_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("household_id", "name_normalized", name="uq_categories_household_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    # Lowercased via Python str.casefold(): SQLite's LOWER() is ASCII-only and
    # would not match Cyrillic duplicates.
    name_normalized: Mapped[str] = mapped_column(String(60))
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_household_created", "household_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    # Author. Never changes, even when the other member edits the record.
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[int]
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # One-time expenses count in reports but never in limit progress or the
    # "typical amount" used for anomaly warnings.
    is_one_time: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # lazy="selectin" keeps handlers free of explicit eager-loading options;
    # plain lazy loading would raise MissingGreenlet under asyncio.
    category: Mapped[Category] = relationship(lazy="selectin")
    author: Mapped[Member] = relationship(lazy="selectin", foreign_keys=[member_id])
    updated_by: Mapped[Member | None] = relationship(lazy="selectin", foreign_keys=[updated_by_id])


class Limit(Base):
    """A spending limit. Append-only: every change or removal inserts a new row.

    The active limit for a (period_type, category_id) pair is its latest row
    with ``effective_from <= now``; ``amount = NULL`` means the limit was
    removed. ``category_id = NULL`` is the household-wide limit.
    """

    __tablename__ = "limits"
    __table_args__ = (
        Index("ix_limits_lookup", "household_id", "period_type", "category_id", "effective_from"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    period_type: Mapped[str] = mapped_column(String(10))  # a budget_bot.periods.Period value
    amount: Mapped[int | None] = mapped_column(nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    category: Mapped[Category | None] = relationship(lazy="selectin")
