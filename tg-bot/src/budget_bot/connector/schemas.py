"""Pydantic models returned by the connector tools — the public API contract.

The MCP SDK publishes them as each tool's output schema and sends results as
structured content, so field names and meanings must stay stable.
"""

import datetime as dt

from pydantic import BaseModel, Field


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
