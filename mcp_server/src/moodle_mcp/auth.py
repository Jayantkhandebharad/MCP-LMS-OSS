"""Act 1 auth: map each caller's bearer token to a Moodle identity.

Over stdio there is one caller — the default client from the lifespan.
Over Streamable HTTP every request may carry `Authorization: Bearer <token>`,
where <token> is that user's Moodle web-service token. We keep one
MoodleClient per distinct token; Moodle's permission system remains the
enforcement backstop for whatever the caller attempts.

(Phase 5 replaces raw Moodle tokens with real OAuth access tokens — this
module is deliberately the only place that will have to change.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from moodle_mcp.moodle_client import MoodleClient

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context


class AuthError(Exception):
    """No usable identity for this request — message is LLM/user-facing."""


class ClientPool:
    """One MoodleClient per bearer token, plus an optional stdio default."""

    def __init__(self, base_url: str, default_token: str | None):
        self._base_url = base_url
        self._clients: dict[str, MoodleClient] = {}
        self._default = MoodleClient(base_url, default_token) if default_token else None

    def for_token(self, token: str) -> MoodleClient:
        if token not in self._clients:
            self._clients[token] = MoodleClient(self._base_url, token)
        return self._clients[token]

    @property
    def default(self) -> MoodleClient | None:
        return self._default

    async def close(self) -> None:
        for client in self._clients.values():
            await client.close()
        if self._default:
            await self._default.close()


def bearer_token(ctx: Context) -> str | None:
    """Extract the bearer token from the HTTP request, if this is HTTP."""
    request = ctx.request_context.request
    if request is None or not hasattr(request, "headers"):
        return None  # stdio: no HTTP request object
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def resolve(ctx: Context) -> MoodleClient:
    """The Moodle identity for THIS request.

    HTTP + bearer  -> that user's client (created on first use)
    stdio          -> the default client from the lifespan
    HTTP, no token -> AuthError telling the caller what to send
    """
    pool: ClientPool = ctx.request_context.lifespan_context.pool
    token = bearer_token(ctx)
    if token:
        return pool.for_token(token)
    if ctx.request_context.request is None and pool.default is not None:
        return pool.default
    raise AuthError(
        "No identity: send 'Authorization: Bearer <your Moodle web-service "
        "token>' with the request. Tokens are minted by the site admin "
        "(Site administration → Server → Manage tokens)."
    )
