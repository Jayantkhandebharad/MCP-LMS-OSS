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
