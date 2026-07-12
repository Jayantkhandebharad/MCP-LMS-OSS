# Brief: I Built an MCP Server for Moodle  (Phase 3)

> Status: **collecting** — phases 0–3 feed this brief. Post gets written in
> `portfolio/src/content/blog/mcp/building-an-mcp-server.tsx` once Phase 3 is done.

## One-line thesis

The reader should understand what MCP actually is (tools/resources/prompts, stdio transport)
by watching a real server get built over a real, messy legacy API — and be able to build one themselves.

## Opening section: project setup (short — 3–4 paragraphs max)

Blog #1 opens with a compressed version of the project story, so readers have context for the whole series:

- **The idea:** instead of another toy weather/todo MCP server, wrap a real system — a self-hosted
  Moodle LMS — with real users, real roles, real permissions. The series builds up to full OAuth 2.1.
- **Why Moodle:** self-hosts in Docker easily; ships courses/topics/quizzes with weightage, enrollment,
  and a genuine role system (Student/Teacher/Manager) out of the box; its famously clunky Web Services
  API makes the tool-design work interesting rather than trivial.
- **The stack:** Python + FastMCP (official SDK), Docker Compose for Moodle + DB, `uv` for tooling.
- **Follow along:** the code is public — https://github.com/Jayantkhandebharad/MCP-LMS-OSS — and each
  post links the commit range it covers, so readers can see the exact state of the project at each phase.

Keep this section short; the meat of the post is the MCP concepts + build.

## Concepts to teach (in depth — this is the point of the series)

- The three MCP primitives — tools vs resources vs prompts, when to use each → *(fill in with our code refs)*
- stdio transport: what actually goes over the wire (JSON-RPC), how a client launches the server
- Tool design for LLM consumers: naming, descriptions, error messages — contrasted against raw Moodle API
- *(add as built)*

## Real issues we hit (capture these THE DAY they happen)

- Bitnami Moodle image moved behind Broadcom's paid program (late 2025) → had to pick an alternative image → *(document which one we chose and why, Phase 1)*
- *(add as they happen — phases 1–2 gotchas land here too)*

## Code moments worth showing

- *(commit hashes / files as built)*

## Diagrams needed

- Overall architecture (AI client → MCP server → Moodle) — exists in CLAUDE.md §3, redraw for the post
- The three primitives mapped onto the LMS domain

## Interview-question angles

- "What are the MCP primitives and when do you use each?"
- "Walk me through what happens on the wire when Claude Desktop calls a tool over stdio."
- "How do you design tools over a bad legacy API?"
