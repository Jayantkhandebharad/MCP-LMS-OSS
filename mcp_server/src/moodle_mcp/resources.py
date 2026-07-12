"""MCP resources: read-only course data addressed by URI.

Resources differ from tools in WHO initiates: the client application attaches
resources as context (a user picks "course://2" from a picker); the model
decides to call tools. Same Moodle data, different access pattern.
"""

from __future__ import annotations

from mcp.server.fastmcp import Context

from moodle_mcp.quiz_parser import html_to_text
from moodle_mcp.server import AppContext, mcp


def _moodle(ctx: Context):
    app: AppContext = ctx.request_context.lifespan_context
    return app.moodle


@mcp.resource("course://{course_id}")
async def course_overview(course_id: int, ctx: Context) -> str:
    """A course's structure: topics and activities, as readable text."""
    sections = await _moodle(ctx).course_contents(course_id)
    lines = [f"Course {course_id}"]
    for s in sections:
        lines.append(f"\nTopic {s['section']}: {s['name']}")
        for m in s.get("modules", []):
            lines.append(f"  - [{m['modname']}] {m['name']}")
    return "\n".join(lines)


@mcp.resource("course://{course_id}/topic/{topic}")
async def topic_material(course_id: int, topic: int, ctx: Context) -> str:
    """The full learning material (page content) of one topic."""
    client = _moodle(ctx)
    sections = await client.course_contents(course_id)
    pages = await client.pages_in_course(course_id)
    wanted = {
        m["instance"]
        for s in sections
        if s["section"] == topic
        for m in s.get("modules", [])
        if m["modname"] == "page"
    }
    parts = [f"{p['name']}\n\n{html_to_text(p['content'])}" for p in pages if p["id"] in wanted]
    return "\n\n---\n\n".join(parts) or f"No page material in topic {topic}."


@mcp.resource("quiz://{quiz_id}")
async def quiz_info(quiz_id: int, ctx: Context) -> str:
    """Quiz metadata: marks, attempt rules, and the user's attempt history."""
    client = _moodle(ctx)
    # The quiz API is course-scoped; find the quiz across enrolled courses.
    for course in await client.my_courses():
        for q in await client.quizzes_in_course(course["id"]):
            if q["id"] == quiz_id:
                attempts = await client.quiz_attempts(quiz_id, status="finished")
                lines = [
                    f"Quiz: {q['name']} (id {quiz_id}) in {course['fullname']}",
                    html_to_text(q.get("intro", "")),
                    f"Total marks: {q['sumgrades']:g}, grade scale: {q['grade']:g}",
                    f"Finished attempts: {len(attempts)}",
                ]
                return "\n".join(filter(None, lines))
    return f"Quiz {quiz_id} not found in your enrolled courses."
