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


mcp = FastMCP("moodle_mcp", lifespan=lifespan, host="127.0.0.1", port=8000)

# Tool/resource/prompt modules register themselves against `mcp` on import.
from moodle_mcp import prompts, resources  # noqa: E402,F401
from moodle_mcp.tools import creator, learner  # noqa: E402,F401

# Replace the stock tools/list handler with the role-gated one (Phase 4).
from moodle_mcp import gating  # noqa: E402

gating.install()


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()  # stdio


if __name__ == "__main__":
    main()
