"""Phase 4 e2e: one HTTP server, many identities.

Spawns the server with --http and connects twice with different bearer
tokens — the same server must answer as different Moodle users. This is the
multi-user property stdio fundamentally cannot have.
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


def _http(headers: dict[str, str]) -> httpx.AsyncClient:
    """The new SDK helper takes a pre-configured httpx client, not headers."""
    return httpx.AsyncClient(headers=headers, timeout=30)

REPO_ROOT = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:8000/mcp"


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
        ["uv", "run", "moodle-mcp", "--http"],
        cwd=REPO_ROOT / "mcp_server",
        env={**os.environ},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):  # wait for the port
        try:
            with socket.create_connection(("127.0.0.1", 8000), timeout=0.2):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail("HTTP server never opened port 8000")
    yield
    proc.terminate()
    proc.wait(timeout=5)


async def _whoami(headers: dict[str, str]) -> str:
    async with streamable_http_client(URL, http_client=_http(headers)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("whoami", {})
            return result.content[0].text


async def test_two_bearers_two_identities(http_server):
    student = await _whoami({"Authorization": f"Bearer {_token('MOODLE_TOKEN_STUDENT1')}"})
    teacher = await _whoami({"Authorization": f"Bearer {_token('MOODLE_TOKEN_TEACHER1')}"})
    assert "student1" in student and "Sam" in student
    assert "teacher1" in teacher and "Tina" in teacher


async def test_no_bearer_is_rejected(http_server):
    text = await _whoami({})
    assert "Bearer" in text  # actionable AuthError, not a stack trace


async def test_tools_work_per_identity(http_server):
    async with streamable_http_client(
        URL, http_client=_http({"Authorization": f"Bearer {_token('MOODLE_TOKEN_TEACHER1')}"})
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("list_my_courses", {})
            text = result.content[0].text
            # teacher1 is enrolled only in INTRO-MCP
            assert "Intro to MCP" in text
            assert "Docker Fundamentals" not in text
