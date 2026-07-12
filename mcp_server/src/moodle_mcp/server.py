"""FastMCP entrypoint for the Moodle MCP server (Phase 3: stdio, single token).

Configuration via environment:
    MOODLE_URL    base URL of the Moodle site (default http://localhost:8080)
    MOODLE_TOKEN  a Moodle web-service token; the server acts AS that user
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from moodle_mcp.moodle_client import MoodleClient


@dataclass
class AppContext:
    moodle: MoodleClient


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
    """One shared Moodle client for the server's lifetime."""
    url = os.environ.get("MOODLE_URL", "http://localhost:8080")
    token = _resolve_token()
    if not token:
        # stdio rule: never write to stdout (it belongs to the protocol)
        print("no Moodle token: set MOODLE_TOKEN or seed docker/.env", file=sys.stderr)
        raise SystemExit(1)
    client = MoodleClient(url, token)
    try:
        yield AppContext(moodle=client)
    finally:
        await client.close()


mcp = FastMCP("moodle_mcp", lifespan=lifespan)

# Tool/resource/prompt modules register themselves against `mcp` on import.
from moodle_mcp import prompts, resources  # noqa: E402,F401
from moodle_mcp.tools import learner  # noqa: E402,F401


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
