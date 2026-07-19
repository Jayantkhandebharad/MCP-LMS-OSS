#!/usr/bin/env python3
"""Capture a REAL MCP sampling round-trip for the blog.

Most MCP clients (incl. Claude Code) don't implement sampling, so we act as a
minimal sampling-capable client: connect to the stdio server, call
generate_practice_quiz, and provide a sampling_callback. The callback captures
the server's ACTUAL sampling request — proving two things authentically:
  1. the server initiated the LLM call (`sampling/createMessage`), and
  2. the untrusted course text arrived FENCED in <UNTRUSTED_COURSE_CONTENT>.

The completion itself is what a sampling-capable client's model would return;
here the demo supplies canned questions so the run is reproducible. We record
the request + response to JSON for the render script.

    python sampling_demo.py   # writes /tmp/sampling-demo.json
"""
import json
import os
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.context import RequestContext
from mcp.types import CreateMessageResult, TextContent

REPO_ROOT = Path(__file__).resolve().parents[2]

# What a sampling-capable client's model would generate from the fenced material.
CANNED = """1. Which MCP primitive does the MODEL decide to call, and may have side effects?
   A) Resource  B) Prompt  **C) Tool**  D) Sampling
   → Tools are model-initiated actions; resources are app-attached, prompts are user-picked.

2. How is a resource addressed?
   A) by function name  **B) by URI, e.g. course://2/topic/1**  C) by numeric id  D) by scope
   → Resources are read-only context addressed by URI.

3. In MCP "sampling", who asks whom to run an LLM completion?
   **A) the server asks the client**  B) the client asks the server
   C) the user asks the IdP  D) the model asks Moodle
   → Sampling is server-initiated; the client stays in control of its model."""


def _token() -> str:
    for line in (REPO_ROOT / "docker" / ".env").read_text().splitlines():
        if line.startswith("MOODLE_TOKEN_STUDENT1="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("seed docker/.env first")


record: dict = {}


async def sampler(context: RequestContext, params):
    """Stand in for the client's model — capture the real request, return text."""
    record["system_prompt"] = params.systemPrompt
    record["user_message"] = next(
        (m.content.text for m in params.messages if isinstance(m.content, TextContent)), ""
    )
    record["max_tokens"] = params.maxTokens
    return CreateMessageResult(
        role="assistant",
        content=TextContent(type="text", text=CANNED),
        model="client-model (demo)",
        stopReason="endTurn",
    )


async def main():
    params = StdioServerParameters(
        command="uv", args=["run", "moodle-mcp"],
        cwd=str(REPO_ROOT / "mcp_server"),
        env={"MOODLE_TOKEN": _token(), "PATH": os.environ["PATH"]},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, sampling_callback=sampler) as session:
            await session.initialize()
            result = await session.call_tool("generate_practice_quiz", {"course_id": 2, "num_questions": 3})
            record["tool_result"] = result.content[0].text
    Path("/tmp/sampling-demo.json").write_text(json.dumps(record, indent=2))
    print("captured sampling round-trip -> /tmp/sampling-demo.json")
    print("system rules present:", "UNTRUSTED_COURSE_CONTENT" in (record["system_prompt"] or ""))
    print("content fenced:", "<UNTRUSTED_COURSE_CONTENT>" in record["user_message"])


if __name__ == "__main__":
    anyio.run(main)
