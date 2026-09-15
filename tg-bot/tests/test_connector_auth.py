import logging

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from budget_bot.connector.auth import AccessTokenError, BearerGate, parse_access_tokens

SERHII_TOKEN = "s" * 40
YULIA_TOKEN = "y" * 40


def test_parses_labelled_tokens_ignoring_spaces_and_a_trailing_comma():
    raw = f" serhii:{SERHII_TOKEN} , yulia:{YULIA_TOKEN},"
    assert parse_access_tokens(raw) == {SERHII_TOKEN: "serhii", YULIA_TOKEN: "yulia"}


@pytest.mark.parametrize(
    ("raw", "hint"),
    [
        ("", "no label:token entries found"),
        (SERHII_TOKEN, "entry 1: expected label:token"),
        (f":{SERHII_TOKEN}", "entry 1: expected label:token"),
        (f"Serhii:{SERHII_TOKEN}", "entry 1: expected label:token"),
        ("serhii:" + "s" * 31, "the token for 'serhii' is shorter than 32 characters"),
        (f"serhii:{SERHII_TOKEN},serhii:{YULIA_TOKEN}", "label 'serhii' is used twice"),
        (f"serhii:{SERHII_TOKEN},yulia:{SERHII_TOKEN}", "'serhii' and 'yulia' share a token"),
    ],
)
def test_malformed_configuration_is_rejected_without_echoing_tokens(raw, hint):
    with pytest.raises(AccessTokenError) as excinfo:
        parse_access_tokens(raw)
    message = str(excinfo.value)
    assert hint in message
    assert "sss" not in message and "yyy" not in message


def gated_app() -> BearerGate:
    async def whoami(request: Request) -> PlainTextResponse:
        return PlainTextResponse(request.state.mcp_token_label)

    app = Starlette(routes=[Route("/mcp", whoami, methods=["POST"])])
    return BearerGate(app, {SERHII_TOKEN: "serhii", YULIA_TOKEN: "yulia"})


@pytest.mark.parametrize(
    ("authorization", "label"),
    [
        (f"Bearer {SERHII_TOKEN}", "serhii"),
        (f"Bearer {YULIA_TOKEN}", "yulia"),
        (f"bearer {SERHII_TOKEN}", "serhii"),
    ],
)
def test_valid_token_reaches_the_app_with_its_label(authorization, label):
    with TestClient(gated_app()) as client:
        response = client.post("/mcp", headers={"Authorization": authorization})
    assert response.status_code == 200
    assert response.text == label


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": f"Bearer {'x' * 40}"},
        {"Authorization": f"Basic {SERHII_TOKEN}"},
        {"Authorization": SERHII_TOKEN},
        {"Authorization": "Bearer"},
    ],
)
def test_request_without_a_valid_bearer_token_gets_a_plain_401(headers):
    with TestClient(gated_app()) as client:
        response = client.post("/mcp", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.text == "Unauthorized"


def test_denials_are_logged_with_reason_and_client_but_never_the_token(caplog):
    with caplog.at_level(logging.WARNING), TestClient(gated_app()) as client:
        client.post("/mcp")
        client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {'x' * 40}",
                "X-Forwarded-For": "203.0.113.7, 10.0.0.1",
            },
        )
    assert [r.getMessage() for r in caplog.records if r.name == "budget_bot.connector.auth"] == [
        "MCP access denied: missing bearer token from testclient",
        "MCP access denied: invalid bearer token from 203.0.113.7",
    ]
    assert "xxx" not in caplog.text
