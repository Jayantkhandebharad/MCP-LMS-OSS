# MCP-LMS-OSS

A production-grade **MCP (Model Context Protocol) server** wrapping a self-hosted **Moodle LMS** — exposing role-gated tools, resources, and prompts to any AI client (Claude Desktop, Claude Code, Cursor, and more).

> 📝 This repo doubles as the reference implementation for a blog series on MCP at [jayantkhd.vercel.app](https://jayantkhd.vercel.app).

## What makes this different from a toy MCP server

- **Role-gated tool lists** — a student and a teacher connecting to the same server see *different tools*. A learner's client never even sees `create_course`.
- **Real auth, done twice** — first with Moodle web-service token mapping, then the full MCP OAuth 2.1 spec (Keycloak, Protected Resource Metadata, scopes, Dynamic Client Registration).
- **All three MCP primitives** — tools, resources (`course://{id}`, `quiz://{id}`), and prompts (`quiz_me`, `study_plan`).
- **Clean tools over a messy legacy API** — Moodle's Web Services API is famously clunky; the MCP layer is where the design work lives.

## Architecture

```
AI client ──(stdio → Streamable HTTP + OAuth 2.1)──▶ MCP Server (Python/FastMCP)
                                                          │
                                     Moodle Web Services (REST)
                                                          ▼
                                        Moodle + DB (Docker Compose)
                                        (+ Keycloak IdP in Phase 5)
```

## Repo layout

| Path | What |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Full project plan, locked decisions, phase roadmap |
| [`docker/`](docker/) | Docker Compose for Moodle + DB (+ Keycloak later) |
| [`mcp_server/`](mcp_server/) | The MCP server (Python, FastMCP, uv-managed) |
| [`docs/briefs/`](docs/briefs/) | Per-phase blog briefs — the posts themselves are published on the blog, not here |
| [`notes/`](notes/) | API cheat-sheets, gotchas, decisions |

## Status

🚧 **Phase 0 complete** — repo scaffolded. Next up: Moodle running in Docker Compose with seeded courses.

See the [phased plan in CLAUDE.md](CLAUDE.md#6-phased-plan-each-phase--checkpoint--blog-post) for the full roadmap.

## Quick start

*(Coming with Phase 1 — everything will be reproducible via `docker compose up` + documented seed steps.)*

## License

MIT for the code in this repo. Moodle itself is GPL and is **not** redistributed here — the compose files pull official/community images.
