"""Learner-facing tools: what a student can do through the MCP server.

Every tool here runs as the user behind MOODLE_TOKEN — Moodle's own permission
system is the enforcement backstop for anything a tool attempts.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from moodle_mcp.moodle_client import MoodleAPIError
from moodle_mcp.server import AppContext, mcp


def _moodle(ctx: Context) -> Any:
    """The shared MoodleClient created in the server lifespan."""
    app: AppContext = ctx.request_context.lifespan_context
    return app.moodle


def _error(e: MoodleAPIError) -> str:
    """Translate raw Moodle errors into messages an LLM can act on."""
    hints = {
        "invalidtoken": "The configured MOODLE_TOKEN is invalid or expired — ask the site admin for a new one.",
        "accessexception": "This function is not enabled for your token's service.",
        "nopermissions": "Your Moodle role does not allow this action.",
    }
    hint = hints.get(e.errorcode, "")
    return f"Error ({e.errorcode}): {e.message} {hint}".strip()


@mcp.tool(
    name="list_my_courses",
    annotations={
        "title": "List My Courses",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_my_courses(ctx: Context) -> str:
    """List all courses the current user is enrolled in.

    Takes no arguments — the user is determined by the server's Moodle token.
    Use this first to discover course ids for other tools.

    Returns:
        Markdown list of courses: id, short name, full name, and progress
        percentage when available. Course ids are the keys for
        get_course_contents and quiz tools.
    """
    try:
        courses = await _moodle(ctx).my_courses()
    except MoodleAPIError as e:
        return _error(e)

    if not courses:
        return "You are not enrolled in any courses."

    lines = [f"# Your courses ({len(courses)})", ""]
    for c in courses:
        progress = f" — progress: {c['progress']:.0f}%" if c.get("progress") is not None else ""
        lines.append(f"- **{c['fullname']}** (id: {c['id']}, shortname: {c['shortname']}){progress}")
    return "\n".join(lines)
