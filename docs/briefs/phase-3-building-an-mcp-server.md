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

- **The three MCP primitives and WHO initiates each** — the framing that makes them click:
  model → tool (`tools/learner.py`), application → resource (`resources.py`),
  user → prompt (`prompts.py`). All three in one server, same underlying data.
- **stdio transport** — the client *spawns the server as a subprocess* and speaks
  JSON-RPC over stdin/stdout. Consequence: stdout belongs to the protocol, so a stray
  `print()` corrupts the session — log to stderr (see `server.py`). Show the
  handshake from `tests/test_stdio_smoke.py`: initialize → list_tools → call_tool.
- **FastMCP mechanics**: `@mcp.tool` turns a function into a tool; the *docstring becomes
  the description the LLM reads* (write docstrings as instructions to an AI, not to a dev);
  `lifespan` holds the shared Moodle client; annotations (readOnlyHint etc.) tell clients
  what's safe.
- **Tool design for LLM consumers** (`submit_quiz_answers` is the case study):
  the LLM answers with option TEXT, the server matches it to Moodle's shuffled radio
  values; wrong text returns the valid options in the error. The AI never sees form
  plumbing. Contrast with the raw API section below.
- **The adapter layer pattern**: every Moodle quirk (PHP array encoding, errors-as-200,
  one-open-attempt) lives in `moodle_client.py` with a comment; tools stay clean.
- **MCP Inspector** as the dev loop: `npx @modelcontextprotocol/inspector -e MOODLE_TOKEN=... uv run moodle-mcp`.

## Real issues we hit (capture these THE DAY they happen)

**Phase 1 (2026-07-12) — standing Moodle up and seeding it:**

- **Bitnami image is paywalled** (Broadcom, late 2025) → chose `erseco/alpine-moodle`:
  actively maintained, ~100MB Alpine, and auto-installs from env vars on first boot.
- **Spaces in `MOODLE_SITENAME` break first-boot install.** The image's install script
  passes the sitename unquoted to `install.php` → `Unrecognised options: Learning Lab`,
  install dies half-way, and you must `docker compose down -v` to retry cleanly.
  Their own default `Dockerized_Moodle` was the tell. Use underscores, rename in UI later.
- **Moodle's Web Services API cannot create activities.** There is no
  `mod_page_create_page` or `mod_quiz_create_quiz` — you can create *courses* and *users*
  via WS but not content. Huge, surprising API gap → we seed content with a PHP script
  inside the container using internal APIs (`add_moduleinfo()`, GIFT question import,
  `quiz_add_quiz_question()` with per-question `maxmark` = weightage). Great framing for
  "the legacy API is messy" section.
- **Moodle 5.x killed course-context question categories.** Question banks are now
  `mod_qbank` activity instances. The old `question_make_default_categories()` sits in
  `deprecatedlib.php` and actually *crashes* (inserts `parent=NULL` into a NOT NULL
  column). New path: `question_bank_helper::get_default_open_instance_system_type($course, true)`
  → `question_get_default_category($qbankcontext->id, true)`.
- **`quiz_update_sumgrades()` removed in 5.x** → 
  `\mod_quiz\quiz_settings::create($id)->get_grade_calculator()->recompute_quiz_sumgrades()`.
- **Moodle 5.2 uses the new `/public` webroot layout** (`/var/www/html/public/...`);
  top-level dirs are remnants. Matters for any in-container path.
- Seed scripts: `docker/seed/seed_phase1.php` (config/users/courses/tokens) and
  `docker/seed/seed_phase1_content.php` (pages/questions/quiz) — both idempotent.

**Phase 2 (2026-07-12) — poking the API by hand (full detail: `notes/api-cheatsheet.md`):**

- **HTTP status is always 200**, errors only in the body — every client must sniff for
  `{"exception": ...}`.
- **Submitting a quiz answer requires parsing rendered HTML.** `mod_quiz_get_attempt_data`
  returns the browser form as HTML; you extract `q{attempt}:{slot}_answer` field names,
  match shuffled options *by label text*, and echo back hidden `sequencecheck` fields.
  Working demo: `notes/scripts/quiz_attempt_demo.py` (scored 6/6 over pure REST).
  This is THE showcase for "clean MCP tools over a messy legacy API".
- **`editingteacher` cannot create courses** — Moodle roles are contextual (course-level
  vs category-level capabilities). Directly shapes Phase 4 RBAC: derive tool lists from
  capabilities, not role names.
- Students must pass their own `userid` to the grades API; omitting it means "everyone"
  and 403s. LLM-facing tools should default to "me".
- `core_webservice_get_site_info` returns the caller's identity + exact callable function
  list — a ready-made "who am I / what can I do" for tool gating.

## Code moments worth showing

The blog has a `<RepoFile path="..." />` component — an inline chip that opens the file
**live from GitHub** in a side panel (series `repoUrl` already points at MCP-LMS-OSS).
Prefer it over pasting long code; use `<CodeBlock>` only for short excerpts discussed line-by-line.

- `<RepoFile path="docker/docker-compose.yml" />` — the whole lab in one file
- `<RepoFile path="docker/seed/seed_phase1.php" />` — web services, users, courses, tokens
- `<RepoFile path="docker/seed/seed_phase1_content.php" />` — the "Moodle WS can't create
  content" workaround: internal APIs + GIFT import + weighted `maxmark`
- `<RepoFile path="mcp_server/src/moodle_mcp/server.py" />` — FastMCP + lifespan, ~50 lines
- `<RepoFile path="mcp_server/src/moodle_mcp/moodle_client.py" />` — the adapter layer
- `<RepoFile path="mcp_server/src/moodle_mcp/quiz_parser.py" />` — HTML → structured questions
- `<RepoFile path="mcp_server/src/moodle_mcp/tools/learner.py" />` — the 9 tools
- `<RepoFile path="mcp_server/tests/test_stdio_smoke.py" />` — the client's-eye view
- Short excerpt candidates for `<CodeBlock>`: the `@mcp.tool` decorator on
  `submit_quiz_answers`; the `_flatten()` PHP-encoding helper; the stderr-only rule.

**Phase 3 build gotchas (2026-07-13):**

- Moodle's `mod_quiz_get_attempt_data` layout string `"1,0,2,0,3,0"` — slots with `0` as
  page separators; you iterate pages, not questions.
- FastMCP registers tools at import time — module import order in `server.py` IS the
  registration mechanism (`from moodle_mcp.tools import learner  # noqa: F401`).
- hatchling refuses to build if `readme = "README.md"` points at a missing file — the
  package needs its own README, not just the repo one.
- Only multichoice questions supported so far; the parser raises a clear error for other
  types (essay etc.) rather than mis-parsing.

## Screenshots (live in THIS repo: `docs/screenshots/` — gallery in its README)

**Generated by script** — `scripts/screenshots/take_screenshots.mjs` logs in as each user
and captures the set headlessly (1400×900 @2x); rerun after any seed change. The blog's
`<Figure>` takes a plain `src`, so reference them straight from this repo:

```
src="https://raw.githubusercontent.com/Jayantkhandebharad/MCP-LMS-OSS/main/docs/screenshots/<file>.png"
```

Shot-list ("what Moodle gives you out of the box", before the MCP layer abstracts it away):

1. `phase1-dashboard.png` — student1's dashboard, both courses
2. `phase1-course.png` — INTRO-MCP course page as student1: three named sections, two pages, quiz
3. `phase1-page.png` — "Tools, Resources, and Prompts" page (the content MCP resources will serve)
4. `phase1-quiz-summary.png` — quiz landing with attempts + grades
5. `phase1-quiz-review.png` — review: Grade 4.00/6.00, per-question marks 1.00/1.00 and 0.00/2.00 (the weightage!)
6. `phase1-grader-report.png` — teacher1's grader report (role contrast)
7. `phase1-ws-functions.png` — admin: mcp_service function list (evidence for the API section)

## Fun tie-in for the writer

The blog already has `<Quiz>`/`<MCQ>` components — embed the *same three questions* from the
Moodle quiz at the end of the post ("the same quiz you just watched me seed — your turn").
Question source: `docker/seed/seed_phase1_content.php` (GIFT block).

## Diagrams needed

- Overall architecture (AI client → MCP server → Moodle) — exists in CLAUDE.md §3, redraw for the post (blog has `Flow`/`Pipeline` components)
- The three primitives mapped onto the LMS domain

## Interview-question angles

- "What are the MCP primitives and when do you use each?"
- "Walk me through what happens on the wire when Claude Desktop calls a tool over stdio."
- "How do you design tools over a bad legacy API?"
