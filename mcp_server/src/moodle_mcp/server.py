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

from mcp.server.fastmcp import FastMCP

from moodle_mcp.moodle_client import MoodleClient


@dataclass
class AppContext:
    moodle: MoodleClient


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """One shared Moodle client for the server's lifetime."""
    url = os.environ.get("MOODLE_URL", "http://localhost:8080")
    token = os.environ.get("MOODLE_TOKEN")
    if not token:
        # stdio rule: never write to stdout (it belongs to the protocol)
        print("MOODLE_TOKEN is required", file=sys.stderr)
        raise SystemExit(1)
    client = MoodleClient(url, token)
    try:
        yield AppContext(moodle=client)
    finally:
        await client.close()


mcp = FastMCP("moodle_mcp", lifespan=lifespan)

# Tool modules register themselves against `mcp` on import.
from moodle_mcp.tools import learner  # noqa: E402,F401


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
