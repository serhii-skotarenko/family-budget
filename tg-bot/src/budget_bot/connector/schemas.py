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
OneTimeFilter = Literal["all", "exclude", "only"]

ONE_TIME_AMOUNT = "Part of the amount marked in the bot as one-time (разова)"


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
    current_monthly_income: int | None = Field(
        None, description="Monthly household income in force now, UAH; null if never set"
    )


class CategorySpending(BaseModel):
    name: str
    amount: int
    share_percent: float = Field(description="Share of the total in percent, one decimal")
    count: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)


class MemberSpending(BaseModel):
    name: str
    amount: int
    count: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)


class SpendingSummary(BaseModel):
    start_date: dt.date
    end_date: dt.date
    category: str | None
    member: str | None
    one_time: OneTimeFilter = "all"
    total: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)
    expense_count: int
    by_category: list[CategorySpending]
    by_member: list[MemberSpending]


class BreakdownItem(BaseModel):
    name: str
    amount: int
    count: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)


class TrendBucket(BaseModel):
    start_date: dt.date
    end_date: dt.date
    partial: bool = Field(description="True when the date range cuts this week or month short")
    total: int
    count: int
    one_time_amount: int = Field(0, description=ONE_TIME_AMOUNT)
    breakdown: list[BreakdownItem] | None


class SpendingTrend(BaseModel):
    start_date: dt.date
    end_date: dt.date
    granularity: Granularity
    split_by: SplitBy
    category: str | None
    member: str | None
    one_time: OneTimeFilter = "all"
    buckets: list[TrendBucket]


class ExpenseItem(BaseModel):
    id: int = Field(description="The number the bot shows as «Витрата #N»")
    datetime: dt.datetime = Field(description="When the expense was recorded, Kyiv time")
    amount: int
    category: str
    member: str = Field(description="Who recorded the expense")
    description: str | None
    is_one_time: bool = Field(False, description="True when marked one-time (разова) in the bot")


class ExpensePage(BaseModel):
    items: list[ExpenseItem]
    total_count: int
    offset: int
    next_offset: int | None = Field(description="Offset of the next page; null on the last page")


LimitStatusName = Literal["ok", "warn", "over"]


class LimitItem(BaseModel):
    category: str | None = Field(description="Category name; null for the household-wide limit")
    amount: int = Field(description="The limit, UAH")
    spent: int = Field(description="Spending in the period without expenses marked one-time")
    percent: int = Field(description="spent * 100 // amount")
    remaining: int = Field(description="amount - spent; negative when over the limit")
    forecast: int = Field(
        description="spent / day_index * days_in_period, rounded; equals spent once complete"
    )
    status: LimitStatusName = Field(
        description="over: percent >= 100; warn: percent >= 80 or forecast > amount; else ok"
    )


class LimitPeriodProgress(BaseModel):
    period_type: Literal["month", "week"]
    start_date: dt.date
    end_date: dt.date
    day_index: int = Field(description="Day of the period the figures are for, from 1")
    days_in_period: int
    complete: bool = Field(description="True when the period has already ended")
    limits: list[LimitItem]


class LimitProgressReport(BaseModel):
    date: dt.date
    periods: list[LimitPeriodProgress] = Field(
        description="The calendar month and the Monday-to-Sunday week containing date, in Kyiv"
    )


class CashflowMonth(BaseModel):
    month_start: dt.date
    month_end: dt.date
    income: int | None = Field(description="Income in force in this month, UAH; null if not set")
    spent: int = Field(description="All expenses of the month, one-time included")
    one_time_amount: int = Field(description=ONE_TIME_AMOUNT)
    free_cashflow: int | None = Field(description="income - spent; null without an income")
    complete: bool = Field(description="True when the month has already ended")


class CashflowReport(BaseModel):
    start_date: dt.date
    end_date: dt.date
    months: list[CashflowMonth] = Field(
        description="Whole calendar months (Kyiv) overlapping the range, up to the current one"
    )
