"""Pydantic models returned by the connector tools — the public API contract.

The MCP SDK publishes them as each tool's output schema and sends results as
structured content, so field names and meanings must stay stable.
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Granularity = Literal["week", "month"]
SplitBy = Literal["none", "category", "member"]
SortOrder = Literal["newest", "oldest", "largest"]


class CategoryInfo(BaseModel):
    name: str
    is_custom: bool = Field(description="False for the bot's default categories")


class BudgetOverview(BaseModel):
    today: dt.date = Field(description="Today's date in Europe/Kyiv")
    timezone: str
    currency: str
    members: list[str]
    categories: list[CategoryInfo]
    first_expense_date: dt.date | None = Field(description="Kyiv date of the earliest expense")
    last_expense_date: dt.date | None = Field(description="Kyiv date of the latest expense")
    expense_count: int


class CategorySpending(BaseModel):
    name: str
    amount: int
    share_percent: float = Field(description="Share of the total in percent, one decimal")
    count: int


class MemberSpending(BaseModel):
    name: str
    amount: int
    count: int


class SpendingSummary(BaseModel):
    start_date: dt.date
    end_date: dt.date
    category: str | None
    member: str | None
    total: int
    expense_count: int
    by_category: list[CategorySpending]
    by_member: list[MemberSpending]


class BreakdownItem(BaseModel):
    name: str
    amount: int
    count: int


class TrendBucket(BaseModel):
    start_date: dt.date
    end_date: dt.date
    partial: bool = Field(description="True when the date range cuts this week or month short")
    total: int
    count: int
    breakdown: list[BreakdownItem] | None


class SpendingTrend(BaseModel):
    start_date: dt.date
    end_date: dt.date
    granularity: Granularity
    split_by: SplitBy
    category: str | None
    member: str | None
    buckets: list[TrendBucket]


class ExpenseItem(BaseModel):
    id: int = Field(description="The number the bot shows as «Витрата #N»")
    datetime: dt.datetime = Field(description="When the expense was recorded, Kyiv time")
    amount: int
    category: str
    member: str = Field(description="Who recorded the expense")
    description: str | None


class ExpensePage(BaseModel):
    items: list[ExpenseItem]
    total_count: int
    offset: int
    next_offset: int | None = Field(description="Offset of the next page; null on the last page")
