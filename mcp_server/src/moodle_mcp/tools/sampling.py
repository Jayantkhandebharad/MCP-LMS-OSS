"""LLM-powered learner tools using MCP *sampling* (server-initiated LLM calls).

Sampling inverts the usual direction: instead of the client's model calling our
tool, our tool asks the client to run a completion on its behalf
(`ctx.session.create_message`). The server never needs its own API key — it
borrows the client's model, and the user's client stays in control (it can
approve, modify, or reject each sampling request).

We use it to go BEYOND the stored course: generate fresh practice questions and
plain-language explanations grounded in the real material. Untrusted course text
is fenced via safety.py before it reaches the model.
"""

from __future__ import annotations

from mcp.server.fastmcp import Context
from mcp.shared.exceptions import McpError
from mcp.types import SamplingMessage, TextContent

from moodle_mcp.moodle_client import MoodleAPIError
from moodle_mcp.safety import SAMPLING_SYSTEM_RULES, wrap_untrusted
from moodle_mcp.server import mcp
from moodle_mcp.tools.learner import _error, _moodle
from moodle_mcp.quiz_parser import html_to_text

_LLM_TOOL = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": False,  # LLM output varies run to run
    "openWorldHint": True,    # reaches the client's model
}

_NO_SAMPLING = (
    "This tool needs your client to support MCP *sampling* (server-initiated "
    "LLM calls), and it doesn't appear to. Try an MCP client that advertises "
    "the sampling capability, or ask me to fetch the raw material instead."
)


async def _sample(ctx: Context, system: str, user: str, *, max_tokens: int = 1000) -> str | None:
    """Run one sampling request; None if the client can't sample."""
    try:
        result = await ctx.session.create_message(
            messages=[SamplingMessage(role="user", content=TextContent(type="text", text=user))],
            system_prompt=system,
            max_tokens=max_tokens,
        )
    except McpError:
        return None  # client didn't grant / doesn't support sampling
    if isinstance(result.content, TextContent):
        return result.content.text
    return getattr(result.content, "text", str(result.content))


async def _topic_text(ctx: Context, course_id: int, topic: int | None) -> str | tuple[str, str]:
    """Concatenated page text for a course/topic, or an error string."""
    client = _moodle(ctx)
    pages = await client.pages_in_course(course_id)
    if topic is not None:
        sections = await client.course_contents(course_id)
        wanted = {
            m["instance"]
            for s in sections
            if s["section"] == topic
            for m in s.get("modules", [])
            if m["modname"] == "page"
        }
        pages = [p for p in pages if p["id"] in wanted]
    return "\n\n".join(f"{p['name']}\n{html_to_text(p['content'])}" for p in pages)


@mcp.tool(
    name="generate_practice_quiz",
    annotations={"title": "Generate a Practice Quiz", **_LLM_TOOL},
)
async def generate_practice_quiz(
    course_id: int, ctx: Context, topic: int | None = None, num_questions: int = 3
) -> str:
    """Create NEW practice questions from a course's real material (LLM-powered).

    Unlike get_quizzes (which returns the stored quiz), this invents fresh
    questions grounded in the actual course pages, using your client's model
    via MCP sampling. Great for extra revision.

    Args:
        course_id: Course id from list_my_courses.
        topic: Optional topic (section) number to focus on; omit for the whole course.
        num_questions: How many questions to generate (1-10).

    Returns:
        Markdown practice questions with answers, or a clear note if your
        client doesn't support sampling.
    """
    num_questions = max(1, min(10, num_questions))
    try:
        material = await _topic_text(ctx, course_id, topic)
    except MoodleAPIError as e:
        return _error(e)
    if not material.strip():
        return (
            f"No readable page material found in course {course_id}"
            + (f", topic {topic}" if topic is not None else "")
            + ". Use get_course_contents to see what's there."
        )

    prompt = (
        f"Write {num_questions} multiple-choice practice questions (4 options "
        "each, mark the correct one and add a one-line explanation) based ONLY "
        "on the reference material below. Vary difficulty.\n\n"
        + wrap_untrusted(material)
    )
    out = await _sample(ctx, SAMPLING_SYSTEM_RULES, prompt, max_tokens=1200)
    if out is None:
        return _NO_SAMPLING
    return f"# Practice quiz (AI-generated from course {course_id})\n\n{out}"


@mcp.tool(name="explain_concept", annotations={"title": "Explain a Concept", **_LLM_TOOL})
async def explain_concept(course_id: int, concept: str, ctx: Context) -> str:
    """Explain a concept in plain language, grounded in the course material.

    Reads the course's real pages and asks your client's model (via sampling)
    to explain the concept simply, using the course's own framing.

    Args:
        course_id: Course id from list_my_courses.
        concept: What to explain, e.g. "MCP resources" or "the confused deputy".

    Returns:
        A beginner-friendly explanation, or a note if sampling is unavailable.
    """
    try:
        material = await _topic_text(ctx, course_id, None)
    except MoodleAPIError as e:
        return _error(e)

    prompt = (
        f"Explain the concept \"{concept}\" to a beginner in 3 short paragraphs. "
        "Ground it in the reference material where relevant; if the material "
        "doesn't cover it, say so and give a careful general explanation.\n\n"
        + wrap_untrusted(material)
    )
    out = await _sample(ctx, SAMPLING_SYSTEM_RULES, prompt, max_tokens=800)
    if out is None:
        return _NO_SAMPLING
    return out
