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


async def test_list_my_courses_as_student():
    params = StdioServerParameters(
        command="uv",
        args=["run", "moodle-mcp"],
        cwd=str(REPO_ROOT / "mcp_server"),
        env={"MOODLE_TOKEN": _token("MOODLE_TOKEN_STUDENT1"), "PATH": __import__("os").environ["PATH"]},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert "list_my_courses" in names

            result = await session.call_tool("list_my_courses", {})
            text = result.content[0].text
            assert "Intro to MCP" in text
            assert "Docker Fundamentals" in text
