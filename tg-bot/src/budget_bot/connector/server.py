"""HTTP side of the Claude connector: configuration, ASGI app and uvicorn server.

The connector runs inside the bot's process (the SQLite volume can be mounted
into only one service), so everything here fails on its own: a bad
configuration or a crashed server is logged, and the bot keeps polling.
"""

import contextlib
import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp

from budget_bot.config import Settings
from budget_bot.connector.auth import AccessTokenError, BearerGate, parse_access_tokens
from budget_bot.connector.tools import SessionFactory, build_mcp_server

logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"
CLAUDE_ORIGIN = "https://claude.ai"
SHUTDOWN_GRACE_SECONDS = 5


@dataclass(frozen=True)
class ConnectorConfig:
    tokens: dict[str, str]  # token -> label
    public_host: str
    port: int


def connector_config(settings: Settings) -> ConnectorConfig | None:
    """The connector's settings, or None (with the reason logged) when it must stay off."""
    raw_tokens = (settings.mcp_access_tokens_raw or "").strip()
    if not raw_tokens:
        logger.info("Claude connector disabled: MCP_ACCESS_TOKENS is not set")
        return None
    try:
        tokens = parse_access_tokens(raw_tokens)
    except AccessTokenError as exc:
        logger.error("Claude connector disabled: MCP_ACCESS_TOKENS is invalid (%s)", exc)
        return None
    public_host = (settings.mcp_public_host or "").strip()
    if not public_host:
        logger.error(
            "Claude connector disabled: MCP_PUBLIC_HOST must be set when MCP_ACCESS_TOKENS is"
        )
        return None
    logger.info(
        "Claude connector enabled on port %d for %s",
        settings.port,
        ", ".join(sorted(tokens.values())),
    )
    return ConnectorConfig(tokens=tokens, public_host=public_host, port=settings.port)


def build_connector_app(
    session_factory: SessionFactory, tokens: Mapping[str, str], public_host: str
) -> ASGIApp:
    """The MCP endpoint behind the bearer-token gate.

    The gate wraps the SDK app directly rather than through a Mount: the SDK
    serves /mcp as an exact route, while a Mount would redirect /mcp to
    /mcp/ — and a redirect drops the Authorization header.
    """
    mcp_app = build_mcp_server(session_factory).streamable_http_app(
        streamable_http_path=MCP_PATH,
        # Plain request/response: no in-memory sessions to lose on a redeploy
        # and no long-lived streams for Railway's edge to cut off.
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_host],
            allowed_origins=[CLAUDE_ORIGIN],
        ),
    )
    return BearerGate(mcp_app, tokens)


class ConnectorServer(uvicorn.Server):
    """uvicorn server that leaves SIGINT/SIGTERM to aiogram.

    Stock uvicorn installs its handlers with signal.signal() when it starts
    and restores the ones it found when it stops. The connector starts before
    aiogram registers its handlers, so after the connector stopped SIGTERM
    would be back to its default action, and a repeated SIGTERM during
    cleanup would kill the process. The bot stops the connector explicitly.
    """

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def build_connector_server(app: ASGIApp, port: int, host: str = "0.0.0.0") -> ConnectorServer:
    return ConnectorServer(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            lifespan="on",
            log_config=None,  # keep the bot's logging setup
            access_log=False,
            server_header=False,
            timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS,
        )
    )


async def serve_connector(server: uvicorn.Server) -> None:
    """Serve until told to exit; never let the connector's failure escape.

    uvicorn calls sys.exit(1) when it cannot bind its port or its lifespan
    fails. A SystemExit raised inside an asyncio task stops the whole event
    loop — and the bot with it — so it is caught here with everything else.
    """
    try:
        await server.serve()
    except (Exception, SystemExit):
        logger.exception("Claude connector stopped; the bot keeps running")
        return
    logger.info("Claude connector stopped")
