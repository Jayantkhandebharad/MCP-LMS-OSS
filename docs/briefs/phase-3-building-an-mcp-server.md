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

## Code moments worth showing

- *(commit hashes / files as built)*

## Diagrams needed

- Overall architecture (AI client → MCP server → Moodle) — exists in CLAUDE.md §3, redraw for the post
- The three primitives mapped onto the LMS domain

## Interview-question angles

- "What are the MCP primitives and when do you use each?"
- "Walk me through what happens on the wire when Claude Desktop calls a tool over stdio."
- "How do you design tools over a bad legacy API?"
