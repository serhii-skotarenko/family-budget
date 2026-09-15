import logging

import pytest
from mcp import Client

from budget_bot.connector.tools import INTERNAL_ERROR_TEXT, build_mcp_server
from budget_bot.db import create_readonly_engine, create_session_factory

SEPTEMBER = {"start_date": "2026-09-01", "end_date": "2026-09-30"}


async def call(session_factory, name: str, arguments: dict | None = None):
    async with Client(build_mcp_server(session_factory)) as client:
        return await client.call_tool(name, arguments or {})


def text_of(result) -> str:
    return "\n".join(block.text for block in result.content)


async def test_every_tool_is_titled_and_read_only(readonly_session_factory):
    async with Client(build_mcp_server(readonly_session_factory)) as client:
        tools = (await client.list_tools()).tools

    assert {tool.name for tool in tools} == {
        "get_budget_overview",
        "summarize_spending",
        "get_spending_trend",
        "list_expenses",
    }
    for tool in tools:
        assert tool.title, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.open_world_hint is False, tool.name


async def test_results_arrive_as_structured_content(early_september, readonly_session_factory):
    result = await call(
        readonly_session_factory,
        "summarize_spending",
        {"start_date": "2026-09-14", "end_date": "2026-09-14", "category": "їжа"},
    )
    assert result.is_error is False
    assert result.structured_content == {
        "start_date": "2026-09-14",
        "end_date": "2026-09-14",
        "category": "Їжа",
        "member": None,
        "total": 1200,
        "expense_count": 1,
        "by_category": [{"name": "Їжа", "amount": 1200, "share_percent": 100.0, "count": 1}],
        "by_member": [{"name": "Оля", "amount": 1200, "count": 1}],
    }


@pytest.mark.parametrize(
    ("tool", "arguments", "hint"),
    [
        (
            "summarize_spending",
            {"start_date": "01.09.2026", "end_date": "2026-09-30"},
            "YYYY-MM-DD",
        ),
        (
            "summarize_spending",
            {"start_date": "2026-09-30", "end_date": "2026-09-01"},
            "is before start_date",
        ),
        ("summarize_spending", {**SEPTEMBER, "category": "Кава"}, "Known categories: Їжа"),
        ("get_spending_trend", {**SEPTEMBER, "member": "Петро"}, "Known members: Сергій, Оля"),
        (
            "get_spending_trend",
            {"start_date": "2020-01-01", "end_date": "2026-12-31", "granularity": "week"},
            'use granularity="month"',
        ),
        ("list_expenses", {**SEPTEMBER, "limit": 500}, "limit must be between 1 and 200"),
        ("list_expenses", {**SEPTEMBER, "offset": -1}, "offset must be 0 or greater"),
        ("list_expenses", {**SEPTEMBER, "min_amount": -5}, "min_amount must be 0 or greater"),
    ],
)
async def test_fixable_mistakes_come_back_as_errors_with_a_hint(
    readonly_session_factory, tool, arguments, hint
):
    result = await call(readonly_session_factory, tool, arguments)
    assert result.is_error is True
    assert hint in text_of(result)


async def test_unexpected_failure_hides_details_and_logs_the_traceback(tmp_path, caplog):
    # SQLite cannot open a missing file read-only: a real failure, not a mock.
    engine = create_readonly_engine(tmp_path / "missing.sqlite3")
    try:
        with caplog.at_level(logging.INFO):
            result = await call(create_session_factory(engine), "get_budget_overview")
    finally:
        await engine.dispose()

    assert result.is_error is True
    assert INTERNAL_ERROR_TEXT in text_of(result)
    assert "unable to open" not in text_of(result)
    failure = next(
        r for r in caplog.records if r.getMessage() == "MCP tool get_budget_overview failed"
    )
    assert failure.exc_info is not None
    assert "MCP tool get_budget_overview by -: internal_error in" in caplog.text


async def test_calls_are_logged_with_their_outcome_but_never_with_data(
    early_september, readonly_session_factory, caplog
):
    with caplog.at_level(logging.INFO):
        await call(readonly_session_factory, "list_expenses", {**SEPTEMBER, "search": "таксі"})
        await call(
            readonly_session_factory, "summarize_spending", {**SEPTEMBER, "category": "Кава"}
        )

    assert "MCP tool list_expenses by -: ok in" in caplog.text
    assert "MCP tool summarize_spending by -: invalid_request in" in caplog.text
    for data in ("таксі", "Таксі", "Кава", "Оля", "Транспорт"):
        assert data not in caplog.text
