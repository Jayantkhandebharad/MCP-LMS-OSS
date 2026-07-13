"""Learner-facing tools: what a student can do through the MCP server.

Every tool here runs as the user behind MOODLE_TOKEN — Moodle's own permission
system is the enforcement backstop for anything a tool attempts.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from moodle_mcp.auth import resolve
from moodle_mcp.moodle_client import MoodleAPIError
from moodle_mcp.quiz_parser import html_to_text, parse_question
from moodle_mcp.server import mcp


def _moodle(ctx: Context) -> Any:
    """The Moodle client for THIS request's identity (bearer token or default)."""
    return resolve(ctx)


def _error(e: MoodleAPIError) -> str:
    """Translate raw Moodle errors into messages an LLM can act on."""
    hints = {
        "invalidtoken": "The configured MOODLE_TOKEN is invalid or expired — ask the site admin for a new one.",
        "accessexception": "This function is not enabled for your token's service.",
        "nopermissions": "Your Moodle role does not allow this action.",
    }
    hint = hints.get(e.errorcode, "")
    return f"Error ({e.errorcode}): {e.message} {hint}".strip()


@mcp.tool(name="whoami", annotations={"title": "Who Am I", **{
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": False,
}})
async def whoami(ctx: Context) -> str:
    """Show which Moodle user this session is acting as.

    Useful to confirm identity before quizzes or grade lookups — over HTTP
    the identity comes from the request's bearer token, so different callers
    get different answers from the same server.
    """
    try:
        info = await _moodle(ctx).site_info()
    except MoodleAPIError as e:
        return _error(e)
    return (
        f"You are **{info['fullname']}** (username: {info['username']}, "
        f"user id: {info['userid']}) on {info['sitename']}."
    )


_READONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


@mcp.tool(name="list_my_courses", annotations={"title": "List My Courses", **_READONLY})
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


@mcp.tool(name="get_course_contents", annotations={"title": "Get Course Contents", **_READONLY})
async def get_course_contents(course_id: int, ctx: Context) -> str:
    """Show the structure of a course: its topics (sections) and activities.

    Args:
        course_id: Course id from list_my_courses.

    Returns:
        Markdown outline of sections with their activities. Each activity shows
        its type and id — use get_topic_material for page content and
        get_quizzes / start_quiz for quizzes. Section numbers are the topic
        numbers used by get_topic_material.
    """
    try:
        sections = await _moodle(ctx).course_contents(course_id)
    except MoodleAPIError as e:
        return _error(e)

    lines = []
    for s in sections:
        lines.append(f"## Topic {s['section']}: {s['name']}")
        summary = html_to_text(s.get("summary", ""))
        if summary:
            lines.append(summary)
        for m in s.get("modules", []):
            lines.append(f"- [{m['modname']}] **{m['name']}** (module id: {m['id']})")
        lines.append("")
    return "\n".join(lines).strip() or f"Course {course_id} has no visible content."


@mcp.tool(name="get_topic_material", annotations={"title": "Get Topic Material", **_READONLY})
async def get_topic_material(course_id: int, topic: int | None, ctx: Context) -> str:
    """Read the learning material (pages) of a course, optionally one topic.

    Args:
        course_id: Course id from list_my_courses.
        topic: Optional topic (section) number from get_course_contents;
            omit to get all pages in the course.

    Returns:
        The full text content of each page in the topic, ready to read,
        summarize, or explain. Pages are the actual study material.
    """
    client = _moodle(ctx)
    try:
        pages = await client.pages_in_course(course_id)
        sections = await client.course_contents(course_id)
    except MoodleAPIError as e:
        return _error(e)

    if topic is not None:
        wanted = {
            m["instance"]
            for s in sections
            if s["section"] == topic
            for m in s.get("modules", [])
            if m["modname"] == "page"
        }
        pages = [p for p in pages if p["id"] in wanted]

    if not pages:
        where = f"topic {topic} of " if topic is not None else ""
        return (
            f"No pages found in {where}course {course_id}. "
            "Use get_course_contents to see what activities exist."
        )

    parts = []
    for p in pages:
        parts.append(f"# {p['name']}\n\n{html_to_text(p['content'])}")
    return "\n\n---\n\n".join(parts)


@mcp.tool(name="get_quizzes", annotations={"title": "Get Quizzes", **_READONLY})
async def get_quizzes(course_id: int, ctx: Context) -> str:
    """List the quizzes of a course with the user's attempts and best grade.

    Args:
        course_id: Course id from list_my_courses.

    Returns:
        Markdown list: quiz id, name, total marks, attempts so far and best
        grade. Use start_quiz with a quiz id to begin or resume an attempt.
    """
    client = _moodle(ctx)
    try:
        quizzes = await client.quizzes_in_course(course_id)
    except MoodleAPIError as e:
        return _error(e)

    if not quizzes:
        return f"Course {course_id} has no quizzes."

    lines = [f"# Quizzes in course {course_id}", ""]
    for q in quizzes:
        try:
            attempts = await client.quiz_attempts(q["id"], status="finished")
        except MoodleAPIError:
            attempts = []
        best = max((a.get("sumgrades") or 0 for a in attempts), default=None)
        best_text = f", best grade: {best:g}/{q['sumgrades']:g}" if attempts else ", not attempted yet"
        lines.append(
            f"- **{q['name']}** (quiz id: {q['id']}) — {q['sumgrades']:g} marks, "
            f"{len(attempts)} finished attempt(s){best_text}"
        )
        intro = html_to_text(q.get("intro", ""))
        if intro:
            lines.append(f"  {intro}")
    return "\n".join(lines)


@mcp.tool(
    name="start_quiz",
    annotations={
        "title": "Start or Resume a Quiz Attempt",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def start_quiz(quiz_id: int, ctx: Context) -> str:
    """Start a quiz attempt (or resume the open one) and show its questions.

    Args:
        quiz_id: Quiz id from get_quizzes.

    Returns:
        The attempt's questions with their options and marks, as markdown.
        Present the questions to the user (or answer them if asked), then call
        submit_quiz_answers with one chosen option text per question number.
    """
    client = _moodle(ctx)
    try:
        attempt = await client.start_or_resume_attempt(quiz_id)
        raw = await client.attempt_pages(attempt)
    except MoodleAPIError as e:
        return _error(e)

    lines = [f"# Quiz attempt {attempt['id']} (quiz {quiz_id})", ""]
    for r in raw:
        q = parse_question(r["slot"], r.get("maxmark", 0), r["html"])
        lines.append(f"## Question {q.slot} ({q.max_mark:g} marks)")
        lines.append(q.text)
        for label in q.options.values():
            lines.append(f"- {label}")
        lines.append("")
    lines.append(
        "Answer with submit_quiz_answers, mapping each question number to the "
        "exact text of the chosen option."
    )
    return "\n".join(lines)


@mcp.tool(
    name="submit_quiz_answers",
    annotations={
        "title": "Submit Quiz Answers",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def submit_quiz_answers(quiz_id: int, answers: dict[int, str], ctx: Context) -> str:
    """Submit answers for the open attempt of a quiz and finish it.

    Args:
        quiz_id: Quiz id from get_quizzes / start_quiz.
        answers: Mapping of question number to the chosen option's text,
            e.g. {1: "Model Context Protocol", 2: "Resources"}. Partial
            matching is fine ("Model Context" matches), case-insensitive.

    Returns:
        The graded result: total score and per-question marks with the
        correct answers where Moodle reveals them.
    """
    client = _moodle(ctx)
    try:
        attempt = await client.start_or_resume_attempt(quiz_id)
        raw = await client.attempt_pages(attempt)

        fields: dict[str, str] = {}
        problems: list[str] = []
        for r in raw:
            q = parse_question(r["slot"], r.get("maxmark", 0), r["html"])
            fields.update(q.hidden_fields)
            chosen = answers.get(q.slot)
            if chosen is None:
                problems.append(f"Question {q.slot} has no answer — it will be left blank.")
                continue
            match = next(
                (v for v, label in q.options.items() if chosen.lower() in label.lower()),
                None,
            )
            if match is None:
                opts = "; ".join(q.options.values())
                return (
                    f"Error: '{chosen}' does not match any option of question "
                    f"{q.slot}. Options are: {opts}. No answers were submitted."
                )
            fields[q.answer_field] = match

        await client.finish_attempt(attempt["id"], fields)
        review = await client.attempt_review(attempt["id"])
    except MoodleAPIError as e:
        return _error(e)

    lines = [f"# Quiz result: {review['grade']:g} marks", ""]
    lines.extend(problems)
    for rq in review["questions"]:
        mark = rq.get("mark", "?")
        lines.append(f"- Question {rq['slot']}: {rq['state']} — {mark}/{rq['maxmark']:g}")
    return "\n".join(lines)


@mcp.tool(name="get_my_grades", annotations={"title": "Get My Grades", **_READONLY})
async def get_my_grades(course_id: int, ctx: Context) -> str:
    """Get the current user's grades for one course.

    Args:
        course_id: Course id from list_my_courses.

    Returns:
        Markdown list of grade items (one per graded activity plus the course
        total): grade, range, and percentage where available.
    """
    try:
        items = await _moodle(ctx).my_grades(course_id)
    except MoodleAPIError as e:
        return _error(e)

    lines = [f"# Grades in course {course_id}", ""]
    for item in items:
        name = item.get("itemname") or "Course total"
        grade = item.get("gradeformatted", "-")
        pct = item.get("percentageformatted", "-")
        lines.append(f"- **{name}**: {grade} ({pct})")
    return "\n".join(lines)


@mcp.tool(name="get_my_progress", annotations={"title": "Get My Progress", **_READONLY})
async def get_my_progress(course_id: int, ctx: Context) -> str:
    """Get activity completion status for the current user in a course.

    Args:
        course_id: Course id from list_my_courses.

    Returns:
        Completion state per activity, or a note if the course doesn't track
        completion (grades via get_my_grades still work then).
    """
    try:
        statuses = await _moodle(ctx).my_completion(course_id)
    except MoodleAPIError as e:
        if e.errorcode in {"completionnotenabled", "nocompletion"}:
            return (
                f"Course {course_id} does not track activity completion. "
                "Use get_my_grades to see performance instead."
            )
        return _error(e)

    if not statuses:
        return f"No completion-tracked activities in course {course_id}."

    done = sum(1 for s in statuses if s["state"])
    lines = [f"# Progress in course {course_id}: {done}/{len(statuses)} activities complete", ""]
    for s in statuses:
        mark = "✅" if s["state"] else "⬜"
        lines.append(f"- {mark} {s.get('activityname', s['cmid'])}")
    return "\n".join(lines)


@mcp.tool(name="search_courses", annotations={"title": "Search Courses", **_READONLY})
async def search_courses(query: str, ctx: Context) -> str:
    """Search the site's course catalog by keyword (name or summary).

    Args:
        query: Search term, e.g. "docker" or "MCP".

    Returns:
        Matching courses with ids — including ones the user is NOT enrolled
        in (enrollment may be required to read their contents).
    """
    try:
        courses = await _moodle(ctx).search_courses(query)
    except MoodleAPIError as e:
        return _error(e)

    if not courses:
        return f"No courses match '{query}'."
    lines = [f"# Courses matching '{query}'", ""]
    for c in courses:
        lines.append(f"- **{c['fullname']}** (id: {c['id']}, shortname: {c['shortname']})")
    return "\n".join(lines)
