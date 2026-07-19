# moodle-mcp

MCP server exposing a self-hosted Moodle LMS as tools, resources, and prompts.
Part of [MCP-LMS-OSS](https://github.com/Jayantkhandebharad/MCP-LMS-OSS) — see the
repo root for the full project plan and the Docker lab it talks to.

## Run (Phase 3: stdio, single token)

```bash
cd mcp_server
uv sync
MOODLE_TOKEN=<token from docker/.env> uv run moodle-mcp
```

Environment:

| Var | Default | Meaning |
|---|---|---|
| `MOODLE_URL` | `http://localhost:8080` | Base URL of the Moodle site |
| `MOODLE_TOKEN` | *(required)* | Moodle web-service token; the server acts as that user |

## Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector -e MOODLE_TOKEN=<token> uv run moodle-mcp
```

## Connect to Claude Code

The repo root has a project-scoped `.mcp.json` — just export the token before
starting a session in this repo:

```bash
export MOODLE_TOKEN=<student or teacher token from docker/.env>
claude
# then: "list my courses", "quiz me on Intro to MCP", ...
```

## Connect to Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "moodle": {
      "command": "uv",
      "args": ["run", "--directory", "/ABS/PATH/TO/MCP-LMS-OSS/mcp_server", "moodle-mcp"],
      "env": {
        "MOODLE_URL": "http://localhost:8080",
        "MOODLE_TOKEN": "<token from docker/.env>"
      }
    }
  }
}
```

Restart Claude Desktop; the hammer icon shows 9 Moodle tools, and the
`/quiz_me` prompt appears in the prompt picker.

## What the server exposes

| Primitive | Names |
|---|---|
| Learner tools | `whoami`, `list_my_courses`, `get_course_contents`, `get_topic_material`, `get_quizzes`, `start_quiz`, `submit_quiz_answers`, `get_my_grades`, `get_my_progress`, `search_courses` |
| Sampling tools (LLM) | `generate_practice_quiz`, `explain_concept` — server-initiated LLM calls; need a client that supports MCP sampling |
| Creator tools (teacher/manager) | `create_course`, `publish_course`, `enrol_student`, `view_course_analytics` |
| Resources | `course://{id}`, `course://{id}/topic/{n}`, `quiz://{id}` |
| Prompts | `quiz_me`, `study_plan`, `explain_like_im_new` |
