"""Bearer-token access to the Claude connector.

MCP_ACCESS_TOKENS holds one ``label:token`` pair per person, so access can be
revoked for one person without touching the other, and logs can say who
called without ever containing a token.
"""

import hmac
import logging
import re
from collections.abc import Mapping

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

MIN_TOKEN_LENGTH = 32
_LABEL = re.compile(r"[a-z0-9_-]{1,32}")


class AccessTokenError(ValueError):
    """MCP_ACCESS_TOKENS is malformed. Messages never include a token."""


def parse_access_tokens(raw: str) -> dict[str, str]:
    """Parse ``label:token,label:token`` into a {token: label} mapping."""
    tokens: dict[str, str] = {}
    for position, chunk in enumerate(raw.split(","), start=1):
        if not chunk.strip():
            continue
        label, separator, token = (part.strip() for part in chunk.partition(":"))
        if not separator or not _LABEL.fullmatch(label):
            raise AccessTokenError(
                f"entry {position}: expected label:token, the label being 1-32 characters "
                "of a-z, 0-9, _ or -"
            )
        if len(token) < MIN_TOKEN_LENGTH:
            raise AccessTokenError(
                f"the token for {label!r} is shorter than {MIN_TOKEN_LENGTH} characters"
            )
        if label in tokens.values():
            raise AccessTokenError(f"label {label!r} is used twice")
        if token in tokens:
            raise AccessTokenError(f"labels {tokens[token]!r} and {label!r} share a token")
        tokens[token] = label
    if not tokens:
        raise AccessTokenError("no label:token entries found")
    return tokens


class BearerGate:
    """ASGI middleware: an HTTP request without a valid bearer token never reaches MCP.

    A rejection is a plain 401 with ``WWW-Authenticate: Bearer`` and nothing
    else — in particular no OAuth ``resource_metadata``, which would send
    Claude looking for an authorization server this connector does not have.
    The label of an accepted token is put into the request state as
    ``mcp_token_label`` for logging.
    """

    def __init__(self, app: ASGIApp, tokens: Mapping[str, str]) -> None:
        self.app = app
        self._tokens = [(token.encode(), label) for token, label in tokens.items()]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return

        presented = _bearer_token(scope)
        label = self._label_for(presented) if presented is not None else None
        if label is None:
            reason = "missing" if presented is None else "invalid"
            logger.warning(
                "MCP access denied: %s bearer token from %s", reason, _client_address(scope)
            )
            await _unauthorized(send)
            return

        scope.setdefault("state", {})["mcp_token_label"] = label
        await self.app(scope, receive, send)

    def _label_for(self, presented: str) -> str | None:
        candidate = presented.encode()
        found = None
        # Compare against every token without stopping early, in constant time.
        for token, label in self._tokens:
            if hmac.compare_digest(candidate, token):
                found = label
        return found


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return value.decode("latin-1")
    return None


def _bearer_token(scope: Scope) -> str | None:
    """The presented credentials; "" when the header is not a usable bearer token."""
    header = _header(scope, b"authorization")
    if header is None:
        return None
    scheme, _, credentials = header.strip().partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return credentials.strip()


def _client_address(scope: Scope) -> str:
    # The last hop is the one our edge proxy appended; earlier ones are client-supplied.
    forwarded = _header(scope, b"x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _unauthorized(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Unauthorized"})
