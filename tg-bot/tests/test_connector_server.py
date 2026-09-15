import logging
import socket

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from budget_bot.config import Settings
from budget_bot.connector.server import (
    ConnectorConfig,
    build_connector_app,
    build_connector_server,
    connector_config,
    serve_connector,
)

TOKEN = "s" * 40
PROTOCOL_VERSION = "2025-11-25"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    },
}


def make_settings(**env) -> Settings:
    return Settings(_env_file=None, TELEGRAM_BOT_TOKEN="123:ABC", ALLOWED_TELEGRAM_IDS="111", **env)


@pytest.mark.parametrize("env", [{}, {"MCP_ACCESS_TOKENS": "   "}])
def test_connector_stays_off_without_tokens(env, caplog):
    with caplog.at_level(logging.INFO):
        assert connector_config(make_settings(**env)) is None
    assert "Claude connector disabled: MCP_ACCESS_TOKENS is not set" in caplog.text


def test_valid_configuration_enables_the_connector():
    settings = make_settings(
        MCP_ACCESS_TOKENS=f"serhii:{TOKEN}", MCP_PUBLIC_HOST="budget.up.railway.app", PORT="9000"
    )
    assert connector_config(settings) == ConnectorConfig(
        tokens={TOKEN: "serhii"}, public_host="budget.up.railway.app", port=9000
    )


def test_malformed_tokens_switch_the_connector_off_loudly(caplog):
    settings = make_settings(MCP_ACCESS_TOKENS="serhii:" + "q" * 10, MCP_PUBLIC_HOST="budget.test")
    with caplog.at_level(logging.INFO):
        assert connector_config(settings) is None
    assert any(
        r.levelno == logging.ERROR
        and "Claude connector disabled: MCP_ACCESS_TOKENS is invalid" in r.getMessage()
        for r in caplog.records
    )
    assert "qqq" not in caplog.text


def test_tokens_without_a_public_host_switch_the_connector_off(caplog):
    with caplog.at_level(logging.ERROR):
        assert connector_config(make_settings(MCP_ACCESS_TOKENS=f"serhii:{TOKEN}")) is None
    assert "MCP_PUBLIC_HOST must be set" in caplog.text


@pytest.fixture
def connector_app(readonly_session_factory):
    # A fresh app per test: the SDK's session manager runs only once per app.
    return build_connector_app(readonly_session_factory, {TOKEN: "serhii"}, "testserver")


async def test_initialize_is_served_on_mcp_without_a_redirect(connector_app):
    with TestClient(connector_app) as client:
        response = client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS, follow_redirects=False)
    assert response.status_code == 200
    assert response.json()["result"]["protocolVersion"] == PROTOCOL_VERSION


async def test_unauthenticated_request_is_refused_without_oauth_metadata(connector_app):
    headers = {k: v for k, v in MCP_HEADERS.items() if k != "Authorization"}
    with TestClient(connector_app) as client:
        response = client.post("/mcp", json=INITIALIZE, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_unexpected_host_is_refused(connector_app):
    with TestClient(connector_app) as client:
        response = client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Host": "evil.example"}
        )
    assert response.status_code == 421


async def test_requests_from_claude_ai_are_accepted(connector_app):
    with TestClient(connector_app) as client:
        response = client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Origin": "https://claude.ai"}
        )
    assert response.status_code == 200


async def test_tool_call_over_http_logs_the_token_label_but_not_the_token(connector_app, caplog):
    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "get_budget_overview", "arguments": {}},
    }
    with caplog.at_level(logging.INFO), TestClient(connector_app) as client:
        response = client.post(
            "/mcp", json=call, headers={**MCP_HEADERS, "MCP-Protocol-Version": PROTOCOL_VERSION}
        )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is False
    assert "MCP tool get_budget_overview by serhii: ok in" in caplog.text
    assert TOKEN not in caplog.text


async def test_connector_that_cannot_bind_its_port_does_not_raise(caplog):
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        server = build_connector_server(
            Starlette(), port=blocker.getsockname()[1], host="127.0.0.1"
        )
        with caplog.at_level(logging.ERROR):
            await serve_connector(server)  # a SystemExit escaping here would fail the test run
    assert "Claude connector stopped; the bot keeps running" in caplog.text
