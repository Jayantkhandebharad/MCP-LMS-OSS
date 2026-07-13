"""Role-gated tool lists: different callers see different tools.

This replaces FastMCP's stock `tools/list` handler with one that asks
"who is asking?" first. A learner's client never even sees create_course —
the tool is absent from the advertised list, not just forbidden.

Layering (all three exist on purpose):
1. THIS module  — visibility: the tool list matches the caller's capabilities
2. creator.py   — guard: hidden-but-called tools still refuse politely
3. Moodle       — enforcement: the API rejects unauthorized calls regardless
"""

from __future__ import annotations

from mcp.types import Tool as MCPTool

from moodle_mcp import auth
from moodle_mcp.server import mcp
from moodle_mcp.tools.creator import CREATOR_TOOLS


async def _caller_is_creator() -> bool:
    """Resolve the CURRENT request's identity and ask Moodle, not a role name."""
    rc = mcp._mcp_server.request_context
    pool = rc.lifespan_context.pool

    token = None
    request = getattr(rc, "request", None)
    if request is not None and hasattr(request, "headers"):
        auth_header = request.headers.get("authorization", "")
        scheme, _, value = auth_header.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            token = value.strip()

    client = pool.for_token(token) if token else pool.default
    if client is None:
        return False  # unauthenticated callers get the learner-only view
    try:
        return await client.can_manage_courses()
    except Exception:
        return False  # bad token etc. — fail closed to the smaller tool set


async def gated_list_tools() -> list[MCPTool]:
    """FastMCP's own conversion, minus creator tools for non-creators."""
    tools = await mcp.list_tools()
    if await _caller_is_creator():
        return tools
    return [t for t in tools if t.name not in CREATOR_TOOLS]


def install() -> None:
    """Swap the stock tools/list handler for the gated one."""
    mcp._mcp_server.list_tools()(gated_list_tools)