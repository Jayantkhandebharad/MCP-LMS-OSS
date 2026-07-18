"""Map each caller to a Moodle identity — both auth acts live here.

Act 1 (MOODLE_MCP_AUTH=act1, default): the HTTP bearer IS a Moodle
web-service token. Simple, real, but non-standard — Blog #2's model.

Act 2 (MOODLE_MCP_AUTH=oauth): the bearer is a Keycloak-issued OAuth 2.1
JWT. The SDK's auth middleware has already validated it (oauth.py) by the
time resolve() runs; here we only map the authenticated USERNAME to that
user's Moodle token from the gitignored docker/.env. The OAuth token is
never forwarded to Moodle — no token passthrough, no confused deputy.

Over stdio there is one caller — the default client from the lifespan.
Moodle's permission system remains the enforcement backstop in every mode.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.auth.middleware.auth_context import get_access_token

from moodle_mcp.moodle_client import MoodleClient

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

AUTH_MODE = os.environ.get("MOODLE_MCP_AUTH", "act1")


def load_user_token_map() -> dict[str, str]:
    """username (lowercase) -> Moodle token, from docker/.env lines like
    MOODLE_TOKEN_STUDENT1=abc123. This mapping is server-side state — the
    whole point is that callers never handle Moodle tokens in Act 2."""
    env_file = Path(__file__).resolve().parents[3] / "docker" / ".env"
    mapping: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("MOODLE_TOKEN_") and "=" in line:
                key, value = line.split("=", 1)
                mapping[key.removeprefix("MOODLE_TOKEN_").lower()] = value.strip()
    return mapping


class AuthError(Exception):
    """No usable identity for this request — message is LLM/user-facing."""


class ClientPool:
    """One MoodleClient per Moodle token, plus an optional stdio default."""

    def __init__(self, base_url: str, default_token: str | None):
        self._base_url = base_url
        self._clients: dict[str, MoodleClient] = {}
        self._default = MoodleClient(base_url, default_token) if default_token else None
        # Act 2: server-side identity map (username -> Moodle token)
        self.user_tokens = load_user_token_map()

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


def _raw_bearer(request) -> str | None:
    if request is None or not hasattr(request, "headers"):
        return None  # stdio: no HTTP request object
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def resolve_from_request_context(request_context) -> MoodleClient:
    """The Moodle identity for THIS request. Works for both auth acts.

    Act 2 (oauth): the SDK middleware already validated the JWT; map its
                   username claim to that user's server-held Moodle token.
    Act 1 (act1):  the raw bearer IS a Moodle token; use it directly.
    stdio (both):  the default client from the lifespan.
    """
    pool: ClientPool = request_context.lifespan_context.pool
    request = getattr(request_context, "request", None)

    if request is None:
        if pool.default is not None:
            return pool.default
        raise AuthError("No identity: set MOODLE_TOKEN or seed docker/.env.")

    if AUTH_MODE == "oauth":
        access = get_access_token()  # set by the SDK's auth middleware
        if access is None:
            raise AuthError("Not authenticated: complete the OAuth flow first.")
        username = (access.claims or {}).get("preferred_username", "").lower()
        moodle_token = pool.user_tokens.get(username)
        if not moodle_token:
            raise AuthError(
                f"'{username or access.subject}' authenticated with Keycloak but has "
                "no Moodle account mapped on this server. Ask the admin to add "
                f"MOODLE_TOKEN_{(username or 'user').upper()} to docker/.env."
            )
        return pool.for_token(moodle_token)

    token = _raw_bearer(request)
    if token:
        return pool.for_token(token)
    raise AuthError(
        "No identity: send 'Authorization: Bearer <your Moodle web-service "
        "token>' with the request. Tokens are minted by the site admin "
        "(Site administration → Server → Manage tokens)."
    )


def resolve(ctx: Context) -> MoodleClient:
    return resolve_from_request_context(ctx.request_context)
