"""MCP tools of the Claude connector: registration, argument checks, call logging."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from budget_bot.clock import utcnow
from budget_bot.connector import analytics
from budget_bot.connector.inputs import (
    InvalidRequest,
    check_limit,
    check_not_negative,
    parse_date_range,
    parse_day,
)
from budget_bot.connector.schemas import (
    BudgetOverview,
    ExpensePage,
    Granularity,
    LimitProgressReport,
    OneTimeFilter,
    SortOrder,
    SpendingSummary,
    SpendingTrend,
    SplitBy,
)
from budget_bot.periods import to_kyiv

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
INTERNAL_ERROR_TEXT = "Internal error while reading budget data; try again later."
SDK_SERVER_LOGGER = "mcp.server.mcpserver.server"

SessionFactory = async_sessionmaker[AsyncSession]

StartDate = Annotated[
    str, Field(description="First day of the range, YYYY-MM-DD, a Kyiv calendar day, inclusive")
]
EndDate = Annotated[
    str, Field(description="Last day of the range, YYYY-MM-DD, a Kyiv calendar day, inclusive")
]
CategoryName = Annotated[
    str | None, Field(description="Only this category, matched by name ignoring case")
]
MemberName = Annotated[
    str | None,
    Field(description="Only expenses recorded by this member, matched by name ignoring case"),
]
OneTimeArg = Annotated[
    OneTimeFilter,
    Field(
        description="all: every expense; exclude: without expenses marked one-time (разова) "
        "in the bot; only: just those"
    ),
]

OVERVIEW_DESCRIPTION = (
    "Returns what the family budget data covers: today's date in Kyiv, the currency (UAH), "
    "household members, expense categories, the dates of the first and last recorded expense "
    "and the number of expenses. Expense dates are when an expense was recorded in the "
    "Telegram bot."
)
SUMMARY_DESCRIPTION = (
    "Returns total spending in whole UAH for an inclusive range of Kyiv calendar days: the "
    "number of expenses, a breakdown by category (amount, share of the total in percent, "
    "count) and a breakdown by member (amount, count). Can be narrowed to one category "
    "and/or one member. Each amount also carries one_time_amount, the part marked one-time "
    "in the bot."
)
TREND_DESCRIPTION = (
    "Returns spending in whole UAH per calendar week (Monday to Sunday) or per calendar "
    "month, in Kyiv time, across an inclusive date range, optionally split by category or "
    "by member. Weeks or months cut short by the range are marked partial. At most 60 "
    "buckets per call. Each bucket and breakdown row also carries one_time_amount, the part "
    "marked one-time in the bot."
)
LIST_DESCRIPTION = (
    "Returns individual expenses for an inclusive range of Kyiv calendar days, one page at a "
    "time: id (the number the bot shows as «Витрата #N»), date and time in Kyiv, amount in "
    "whole UAH, category, the member who recorded it and the description. Filters: category, "
    "member, a case-insensitive text in the description, a minimum amount. Sorted newest "
    "first, oldest first or largest first. Each item says whether it is marked one-time in "
    "the bot."
)

LIMITS_DESCRIPTION = (
    "Returns spending limits set in the bot with their progress, for the calendar month and "
    "the Monday-to-Sunday week (Kyiv time) containing the given day, today by default: the "
    "limit in whole UAH, spending so far without expenses marked one-time, percent used, "
    "remaining, a linear forecast for the whole period and a status. A past period uses the "
    "limits in force at its end. Category null means the household-wide limit."
)


def build_mcp_server(session_factory: SessionFactory) -> MCPServer:
    # The SDK logs the text of every ToolError at INFO, and ours name categories
    # and members. Its warnings and errors still get through.
    logging.getLogger(SDK_SERVER_LOGGER).setLevel(logging.WARNING)
    server = MCPServer(name="family-budget")

    @server.tool(
        name="get_budget_overview",
        title="Огляд бюджету",
        description=OVERVIEW_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def get_budget_overview(ctx: Context) -> BudgetOverview:
        async def work(session: AsyncSession) -> BudgetOverview:
            return await analytics.budget_overview(session, now_utc=utcnow())

        return await _run("get_budget_overview", ctx, session_factory, work)

    @server.tool(
        name="summarize_spending",
        title="Підсумок витрат",
        description=SUMMARY_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def summarize_spending(
        ctx: Context,
        start_date: StartDate,
        end_date: EndDate,
        category: CategoryName = None,
        member: MemberName = None,
        one_time: OneTimeArg = "all",
    ) -> SpendingSummary:
        async def work(session: AsyncSession) -> SpendingSummary:
            date_range = parse_date_range(start_date, end_date)
            return await analytics.summarize_spending(
                session,
                date_range,
                category=await analytics.find_category(session, category),
                member=await analytics.find_member(session, member),
                one_time=one_time,
            )

        return await _run("summarize_spending", ctx, session_factory, work)

    @server.tool(
        name="get_spending_trend",
        title="Динаміка витрат",
        description=TREND_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def get_spending_trend(
        ctx: Context,
        start_date: StartDate,
        end_date: EndDate,
        granularity: Annotated[
            Granularity,
            Field(description="week: Monday to Sunday; month: calendar month; both in Kyiv time"),
        ] = "month",
        split_by: Annotated[
            SplitBy, Field(description="Add a per-bucket breakdown by category or by member")
        ] = "none",
        category: CategoryName = None,
        member: MemberName = None,
        one_time: OneTimeArg = "all",
    ) -> SpendingTrend:
        async def work(session: AsyncSession) -> SpendingTrend:
            date_range = parse_date_range(start_date, end_date)
            return await analytics.spending_trend(
                session,
                date_range,
                granularity=granularity,
                split_by=split_by,
                category=await analytics.find_category(session, category),
                member=await analytics.find_member(session, member),
                one_time=one_time,
            )

        return await _run("get_spending_trend", ctx, session_factory, work)

    @server.tool(
        name="list_expenses",
        title="Список витрат",
        description=LIST_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def list_expenses(
        ctx: Context,
        start_date: StartDate,
        end_date: EndDate,
        category: CategoryName = None,
        member: MemberName = None,
        search: Annotated[
            str | None, Field(description="Text to look for in descriptions, ignoring case")
        ] = None,
        min_amount: Annotated[
            int | None, Field(description="Only expenses of at least this many UAH")
        ] = None,
        one_time: OneTimeArg = "all",
        sort: Annotated[
            SortOrder, Field(description="newest first, oldest first or largest amount first")
        ] = "newest",
        limit: Annotated[int, Field(description="Page size, 1 to 200")] = 50,
        offset: Annotated[
            int, Field(description="Expenses to skip: next_offset from the previous page")
        ] = 0,
    ) -> ExpensePage:
        async def work(session: AsyncSession) -> ExpensePage:
            date_range = parse_date_range(start_date, end_date)
            check_limit(limit)
            check_not_negative("offset", offset)
            check_not_negative("min_amount", min_amount)
            return await analytics.list_expenses(
                session,
                date_range,
                category=await analytics.find_category(session, category),
                member=await analytics.find_member(session, member),
                search=search,
                min_amount=min_amount,
                sort=sort,
                limit=limit,
                offset=offset,
                one_time=one_time,
            )

        return await _run("list_expenses", ctx, session_factory, work)

    @server.tool(
        name="get_limit_progress",
        title="Прогрес лімітів",
        description=LIMITS_DESCRIPTION,
        annotations=READ_ONLY,
    )
    async def get_limit_progress(
        ctx: Context,
        date: Annotated[
            str | None,
            Field(description="A Kyiv calendar day, YYYY-MM-DD, not in the future; default today"),
        ] = None,
    ) -> LimitProgressReport:
        async def work(session: AsyncSession) -> LimitProgressReport:
            now = utcnow()
            day = parse_day("date", date) if date is not None else to_kyiv(now).date()
            return await analytics.limit_progress_report(session, day, now_utc=now)

        return await _run("get_limit_progress", ctx, session_factory, work)

    return server


async def _run[T](
    name: str,
    ctx: Context,
    session_factory: SessionFactory,
    work: Callable[[AsyncSession], Awaitable[T]],
) -> T:
    """Run one tool call in its own read session and log how it ended.

    InvalidRequest becomes a ToolError the model can act on. Anything else is
    logged with its traceback and reported without internals. The log line
    never carries arguments or results: they are the family's financial data.
    """
    started = time.perf_counter()
    outcome = "internal_error"
    try:
        async with session_factory() as session:
            result = await work(session)
        outcome = "ok"
        return result
    except InvalidRequest as exc:
        outcome = "invalid_request"
        raise ToolError(str(exc)) from None
    except Exception:
        logger.exception("MCP tool %s failed", name)
        raise ToolError(INTERNAL_ERROR_TEXT) from None
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "MCP tool %s by %s: %s in %.0f ms", name, _token_label(ctx), outcome, elapsed_ms
        )


def _token_label(ctx: Context) -> str:
    """Label of the bearer token that authenticated this HTTP call (set by BearerGate)."""
    request = ctx.request_context.request
    if request is None:  # in-process calls, e.g. tests
        return "-"
    return getattr(request.state, "mcp_token_label", "-")
