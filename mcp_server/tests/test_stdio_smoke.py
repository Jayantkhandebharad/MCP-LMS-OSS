"""End-to-end smoke test: spawn the server over stdio and call a tool.

This is the same handshake Claude Desktop performs — if this passes, the
server speaks real MCP. Requires the Docker Moodle lab to be running and
tokens present in ../docker/.env.
"""

from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[2]


def _token(name: str) -> str:
    env_file = REPO_ROOT / "docker" / ".env"
    if not env_file.exists():
        pytest.skip("docker/.env not found — seed the lab first")
    for line in env_file.read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    pytest.skip(f"{name} not in docker/.env")


def _student_params() -> StdioServerParameters:
    return StdioServerParameters(
        command="uv",
        args=["run", "moodle-mcp"],
        cwd=str(REPO_ROOT / "mcp_server"),
        env={"MOODLE_TOKEN": _token("MOODLE_TOKEN_STUDENT1"), "PATH": __import__("os").environ["PATH"]},
    )


async def test_full_surface_as_student():
    """One session exercising tools, resources, and prompts end to end."""
    async with stdio_client(_student_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- the three primitives are all advertised ---
            tools = {t.name for t in (await session.list_tools()).tools}
            assert {
                "list_my_courses", "get_course_contents", "get_topic_material",
                "get_quizzes", "start_quiz", "submit_quiz_answers",
                "get_my_grades", "get_my_progress", "search_courses",
            } <= tools

            prompts = {p.name for p in (await session.list_prompts()).prompts}
            assert {"quiz_me", "study_plan", "explain_like_im_new"} <= prompts

            templates = await session.list_resource_templates()
            uris = {t.uriTemplate for t in templates.resourceTemplates}
            assert "course://{course_id}" in uris

            # --- tools return real seeded data ---
            text = (await session.call_tool("list_my_courses", {})).content[0].text
            assert "Intro to MCP" in text and "Docker Fundamentals" in text

            text = (await session.call_tool("get_course_contents", {"course_id": 2})).content[0].text
            assert "MCP Primitives" in text

            text = (await session.call_tool("get_topic_material", {"course_id": 2, "topic": 2})).content[0].text
            assert "three primitives" in text.lower()

            # --- resource read ---
            res = await session.read_resource("course://2/topic/1")
            assert "Model Context Protocol" in res.contents[0].text


async def test_quiz_attempt_via_mcp():
    """The crown jewel: take the whole quiz through MCP and score 6/6."""
    async with stdio_client(_student_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            text = (await session.call_tool("start_quiz", {"quiz_id": 1})).content[0].text
            assert "Question 1" in text and "Question 3" in text

            result = await session.call_tool(
                "submit_quiz_answers",
                {
                    "quiz_id": 1,
                    "answers": {
                        1: "Model Context Protocol",
                        2: "Resources",
                        3: "The server asks the client",
                    },
                },
            )
            text = result.content[0].text
            assert "6 marks" in text
            assert text.count("gradedright") == 3


async def test_grades_and_wrong_answer_feedback():
    async with stdio_client(_student_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            text = (await session.call_tool("get_my_grades", {"course_id": 2})).content[0].text
            assert "MCP Basics Quiz" in text and "Course total" in text

            # Non-matching answer text -> actionable error, nothing submitted.
            result = await session.call_tool(
                "submit_quiz_answers",
                {"quiz_id": 1, "answers": {1: "Blockchain Protocol"}},
            )
            text = result.content[0].text
            assert "does not match any option" in text
