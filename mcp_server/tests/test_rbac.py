"""Phase 4 RBAC: the tool list itself changes with the caller's identity.

The headline demo of the whole project: student1 and teacher1 hit the SAME
HTTP server and receive different tool lists — and the hidden tools refuse
politely even if called blind.
"""

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from moodle_mcp.moodle_client import MoodleClient

REPO_ROOT = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:8001/mcp"


def _token(name: str) -> str:
    env_file = REPO_ROOT / "docker" / ".env"
    if not env_file.exists():
        pytest.skip("docker/.env not found — seed the lab first")
    for line in env_file.read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    pytest.skip(f"{name} not in docker/.env")


@pytest.fixture(scope="module")
def http_server():
    proc = subprocess.Popen(
        ["uv", "run", "python", "-c",
         "from moodle_mcp.server import mcp; mcp.settings.port = 8001; "
         "mcp.run(transport='streamable-http')"],
        cwd=REPO_ROOT / "mcp_server",
        env={**os.environ},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", 8001), timeout=0.2):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail("HTTP server never opened port 8001")
    yield
    proc.terminate()
    proc.wait(timeout=5)


def _session(token: str):
    return streamable_http_client(
        URL, http_client=httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30)
    )


async def _tool_names(token: str) -> set[str]:
    async with _session(token) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return {t.name for t in (await session.list_tools()).tools}


async def test_tool_list_differs_by_identity(http_server):
    student_tools = await _tool_names(_token("MOODLE_TOKEN_STUDENT1"))
    teacher_tools = await _tool_names(_token("MOODLE_TOKEN_TEACHER1"))

    # the learner surface is common to both
    assert {"list_my_courses", "start_quiz", "get_my_grades"} <= student_tools
    assert student_tools <= teacher_tools

    # creator tools exist ONLY for the teacher — a student's client never sees them
    creator = {"create_course", "publish_course", "enrol_student", "view_course_analytics"}
    assert creator & student_tools == set()
    assert creator <= teacher_tools


async def test_hidden_tool_refuses_when_called_blind(http_server):
    """Filtering is UX; the guard must hold even for a client that ignores it."""
    async with _session(_token("MOODLE_TOKEN_STUDENT1")) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "create_course",
                {"fullname": "Sneaky", "shortname": "SNEAK-1", "summary": "nope"},
            )
            text = result.content[0].text
            assert "course-management rights" in text


async def _delete_course_by_shortname(shortname: str) -> None:
    """Admin cleanup helper — makes the workflow test repeatable."""
    admin = MoodleClient("http://localhost:8080", _token("MOODLE_TOKEN_ADMIN"))
    try:
        found = await admin.call(
            "core_course_get_courses_by_field", field="shortname", value=shortname
        )
        for course in found["courses"]:
            await admin.call("core_course_delete_courses", courseids=[course["id"]])
    finally:
        await admin.close()


async def test_teacher_full_workflow(http_server):
    """Teacher: create -> enrol -> publish -> analytics. Then admin cleans up."""
    await _delete_course_by_shortname("RBAC-TEST")  # in case a prior run died midway
    async with _session(_token("MOODLE_TOKEN_TEACHER1")) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            text = (await session.call_tool("create_course", {
                "fullname": "RBAC Test Course", "shortname": "RBAC-TEST",
                "summary": "Created by the Phase 4 test suite.",
            })).content[0].text
            assert "Created course" in text and "HIDDEN" in text
            course_id = int(text.split("(id: ")[1].split(",")[0])

            text = (await session.call_tool(
                "enrol_student", {"course_id": course_id, "email": "student1@example.com"}
            )).content[0].text
            assert "Enrolled Sam Student" in text

            text = (await session.call_tool(
                "publish_course", {"course_id": course_id, "visible": True}
            )).content[0].text
            assert "visible to students" in text

            text = (await session.call_tool(
                "view_course_analytics", {"course_id": course_id}
            )).content[0].text
            assert "Sam Student" in text

    await _delete_course_by_shortname("RBAC-TEST")


async def test_student_analytics_blocked_by_guard(http_server):
    async with _session(_token("MOODLE_TOKEN_STUDENT1")) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            text = (await session.call_tool(
                "view_course_analytics", {"course_id": 2}
            )).content[0].text
            assert "course-management rights" in text