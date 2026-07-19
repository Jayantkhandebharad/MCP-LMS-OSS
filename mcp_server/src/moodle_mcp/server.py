"""FastMCP entrypoint for the Moodle MCP server.

Transports (Phase 4):
    moodle-mcp             stdio (single identity: MOODLE_TOKEN or docker/.env)
    moodle-mcp --http      Streamable HTTP on 127.0.0.1:8000/mcp — each request
                           carries its own `Authorization: Bearer <moodle-token>`

Configuration via environment:
    MOODLE_URL    base URL of the Moodle site (default http://localhost:8080)
    MOODLE_TOKEN  default identity for stdio (fallback: docker/.env)
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from moodle_mcp.auth import ClientPool


@dataclass
class AppContext:
    pool: ClientPool


def _resolve_token() -> str | None:
    """MOODLE_TOKEN env var, else the lab's gitignored docker/.env.

    The fallback (student1's token) means a fresh clone with the Docker lab
    seeded works with zero manual env setup. Env expansion in client configs
    is unreliable (GUI apps don't see your shell), so don't depend on it.
    """
    token = os.environ.get("MOODLE_TOKEN", "").strip()
    if token and not token.startswith("${"):
        return token
    env_file = Path(__file__).resolve().parents[3] / "docker" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(("MOODLE_TOKEN=", "MOODLE_TOKEN_STUDENT1=")):
                print(f"using token from {env_file}", file=sys.stderr)
                return line.split("=", 1)[1].strip()
    return None


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """A pool of per-identity Moodle clients for the server's lifetime.

    The default (stdio) identity is optional: over HTTP every request brings
    its own bearer token, so the server can start without any token at all.
    """
    url = os.environ.get("MOODLE_URL", "http://localhost:8080")
    pool = ClientPool(url, default_token=_resolve_token())
    try:
        yield AppContext(pool=pool)
    finally:
        await pool.close()


def _auth_config() -> dict:
    """Act 2 (MOODLE_MCP_AUTH=oauth): run as an OAuth 2.1 resource server.

    The SDK then mounts /.well-known/oauth-protected-resource (RFC 9728)
    and challenges unauthenticated requests with a WWW-Authenticate header
    pointing at it — which is exactly how MCP clients discover Keycloak.
    """
    if os.environ.get("MOODLE_MCP_AUTH", "act1") != "oauth":
        return {}
    from pydantic import AnyHttpUrl

    from mcp.server.auth.settings import AuthSettings
    from moodle_mcp.oauth import KeycloakTokenVerifier

    issuer = os.environ.get("KEYCLOAK_ISSUER", "http://localhost:8081/realms/mcp-lms")
    resource = os.environ.get("MCP_RESOURCE_URL", "http://127.0.0.1:8000/mcp")
    return {
        "token_verifier": KeycloakTokenVerifier(issuer, resource),
        "auth": AuthSettings(
            issuer_url=AnyHttpUrl(issuer),
            resource_server_url=AnyHttpUrl(resource),
            required_scopes=["lms:read"],
        ),
    }


mcp = FastMCP("moodle_mcp", lifespan=lifespan, host="127.0.0.1", port=8000, **_auth_config())

# Tool/resource/prompt modules register themselves against `mcp` on import.
from moodle_mcp import prompts, resources  # noqa: E402,F401
from moodle_mcp.tools import creator, learner, sampling  # noqa: E402,F401

# Replace the stock tools/list handler with the role-gated one (Phase 4).
from moodle_mcp import gating  # noqa: E402

gating.install()


PRM_PATH = "/.well-known/oauth-protected-resource/mcp"


def _advertise_extra_scopes(app) -> None:
    """Widen the advertised scopes without widening what we REQUIRE.

    The SDK ties Protected Resource Metadata `scopes_supported` to
    `required_scopes` (which we enforce = ["lms:read"]). But a real MCP
    client (Claude Code) also wants `offline_access` for a refresh token,
    and Keycloak only grants a dynamically-registered client the scopes it
    requested at registration — which it derives from this metadata. So a
    scope we don't advertise can never be obtained.

    Fix: advertise lms:read + lms:write + offline_access, keep requiring only
    lms:read. Advertise ≠ require — the classic distinction the coupling hides.
    """
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    resource = os.environ.get("MCP_RESOURCE_URL", "http://127.0.0.1:8000/mcp")
    issuer = os.environ.get("KEYCLOAK_ISSUER", "http://localhost:8081/realms/mcp-lms")
    metadata = {
        "resource": resource,
        "authorization_servers": [issuer],
        "scopes_supported": ["lms:read", "lms:write", "offline_access"],
        "bearer_methods_supported": ["header"],
    }

    async def prm(_request):
        return JSONResponse(metadata, headers={"Access-Control-Allow-Origin": "*"})

    routes = app.router.routes
    for i, route in enumerate(routes):
        if getattr(route, "path", None) == PRM_PATH:
            routes[i] = Route(PRM_PATH, prm, methods=["GET", "OPTIONS"])
            break


def main() -> None:
    if "--http" not in sys.argv:
        mcp.run()  # stdio
        return
    if os.environ.get("MOODLE_MCP_AUTH", "act1") != "oauth":
        mcp.run(transport="streamable-http")
        return
    # OAuth mode: build the app, widen advertised scopes, then serve.
    import uvicorn

    app = mcp.streamable_http_app()
    _advertise_extra_scopes(app)
    uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port,
                log_level=mcp.settings.log_level.lower())


if __name__ == "__main__":
    main()
