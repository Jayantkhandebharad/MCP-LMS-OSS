"""MCP prompts: user-invoked conversation templates.

The third primitive — the USER picks these explicitly (e.g. a /quiz_me
command in the client UI), unlike tools (model-initiated) and resources
(application-attached).
"""

from __future__ import annotations

from moodle_mcp.server import mcp


@mcp.prompt(name="quiz_me", title="Quiz me on a course")
def quiz_me(course: str = "") -> str:
    """Drill the user with practice questions based on course material."""
    target = f"the course '{course}'" if course else "one of my courses (ask me which)"
    return (
        f"Quiz me on {target}. Use list_my_courses and get_topic_material to read "
        "the actual material first, then ask me questions ONE AT A TIME, wait for "
        "my answer, tell me if I'm right with a short explanation, and keep score. "
        "Base questions on the real content, not general knowledge. After 5 "
        "questions, summarize my weak spots and suggest what to reread."
    )


@mcp.prompt(name="study_plan", title="Build me a study plan")
def study_plan(course: str = "", days: int = 7) -> str:
    """Generate a day-by-day study plan from real course structure and progress."""
    target = f"'{course}'" if course else "my enrolled courses (list them first)"
    return (
        f"Build me a {days}-day study plan for {target}. Ground it in reality: "
        "use get_course_contents for the topics, get_topic_material to judge how "
        "dense each one is, and get_my_grades / get_my_progress to see where I "
        "stand. Output a day-by-day markdown table with concrete goals, ending "
        "with quiz attempts as checkpoints."
    )


@mcp.prompt(name="explain_like_im_new", title="Explain a topic simply")
def explain_like_im_new(topic: str) -> str:
    """Explain a course topic assuming zero background knowledge."""
    return (
        f"Read the actual course material about '{topic}' using get_topic_material "
        "(find the right course/topic via list_my_courses and get_course_contents "
        "if needed). Then explain it to me like I'm completely new: everyday "
        "analogies first, jargon defined the moment it appears, and a 3-bullet "
        "recap at the end. Quiz me with one quick question to check I got it."
    )
