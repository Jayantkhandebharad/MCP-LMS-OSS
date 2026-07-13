# Brief: RBAC in MCP — Different Tools for Different Users  (Phase 4 → Blog #2)

> Status: **collecting** (started 2026-07-13). Post target:
> `portfolio/src/content/blog/mcp/rbac-in-mcp.tsx`. Prerequisite posts: 1a + 1b.
> Same audience and language bar as Blog #1: third-year student, define terms,
> short sentences.

## One-line thesis

The reader watches one server show DIFFERENT tool lists to different callers —
and learns that real RBAC is three layers (visibility, guard, enforcement),
with identity carried per-request over Streamable HTTP.

## The demo that carries the post

Same running server, two curl-level differences (`Authorization: Bearer <student>` vs
`<teacher>`): student's `tools/list` has 10 tools; teacher's has 14, including
`create_course`. The student's client doesn't see a disabled button — the tool
*does not exist* in their world. Then the teacher runs create → enrol → publish →
analytics end-to-end. Tests: `mcp_server/tests/test_rbac.py` (all assertions ARE
the demo script).

## Concepts to teach

- **stdio vs Streamable HTTP is an identity model change**: stdio = one subprocess
  per user, identity fixed at spawn; HTTP = one server, identity is per-request
  state (the bearer header). RBAC is only *possible* with the latter.
- **Act-1 auth (token mapping)**: bearer token = Moodle web-service token = a user.
  `auth.py` keeps one MoodleClient per distinct token (ClientPool). Explicitly NOT
  OAuth yet — that's Blog #3; the module docstring even says "only this file changes."
- **Derive permissions from capabilities, not role names.** Two-part lesson:
  (a) our own Phase 2 cheat-sheet was WRONG — site_info's function list is
  service-scoped, identical for every token in the same service; useless for RBAC.
  Correcting your own published assumption is good content.
  (b) the right signal: `core_course_get_user_administration_options` returns
  capability-derived booleans (`update: true/false`) — teacher shows true, student
  false. Creator = site admin OR can update ≥1 course. (`moodle_client.can_manage_courses`)
- **Three security layers, on purpose** (`gating.py` docstring): visibility
  (filtered tools/list), guard (hidden tools refuse politely when called blind —
  test proves a "sneaky" client gets stopped), enforcement (Moodle rejects
  regardless — the backstop that makes bugs in layers 1-2 non-catastrophic).
- **How the gating is implemented**: FastMCP registers protocol handlers in
  `_setup_handlers`; re-registering `tools/list` swaps in our filter
  (`gating.install()`). ~50 lines total.

## Real issues we hit (2026-07-13 — the day they happened)

1. **WS `create_courses` does not auto-assign the creator** to the new course
   (the web UI does!) — teacher created a hidden course they couldn't even open.
   Fix: self-assign editingteacher via `core_role_assign_roles` right after create.
2. **The `require_login` wall**: even role-assign needs to "enter" the course —
   coursecreator archetype lacks `moodle/course:view` + `viewhiddencourses`.
   Granted both in seed (documented as a deliberate site-policy decision).
3. **`role:assign` is TWO gates**: the capability AND the allow-assign matrix
   (`role_allow_assign` table / "Allow role assignments" admin tab). Had to add
   coursecreator→editingteacher to the matrix. Nobody expects the second gate.
4. **Teachers can't search users site-wide** — `core_user_get_users_by_field`
   silently returns [] (no error!). And in participant lists teachers see
   **email + fullname but never username**. Consequence: `enrol_student` takes an
   email, with a two-tier lookup (site-wide for admins → scan own courses' participants).
   Tool design following permission reality.
5. **"Message was not sent." breaking enrolment**: no SMTP in the lab → Moodle's
   enrolment notification email throws INSIDE the WS call. Fix: `noemailever=1`.
   Classic self-hosted trap.
6. Leftover test data breaks reruns → tests self-clean by shortname before and after
   (idempotence discipline again).
7. SDK churn: `streamablehttp_client` deprecated mid-phase; the replacement
   `streamable_http_client` takes a pre-configured `httpx.AsyncClient` instead of
   a headers kwarg.

## Code moments (RepoFile embeds)

- `mcp_server/src/moodle_mcp/auth.py` — ClientPool + resolve(); the Act-1 contract
- `mcp_server/src/moodle_mcp/gating.py` — the whole point of the post in one file
- `mcp_server/src/moodle_mcp/tools/creator.py` — guard pattern + the enrol-by-email design
- `mcp_server/src/moodle_mcp/moodle_client.py` — `can_manage_courses()` capability check
- `docker/seed/seed_phase4.php` — the role plumbing as reproducible admin actions
- `mcp_server/tests/test_rbac.py` — the demo as assertions

## Screenshots (DONE — in docs/screenshots/, same raw URL pattern as always)

- `phase4-tools-diff.png` — THE hero: side-by-side live tools/list responses,
  10 vs 14, creator tools highlighted. Open the post with it.
- `phase4-tools-student.png` / `phase4-tools-teacher.png` — individual panels.
- `phase4-teacher-demo.png` — REAL headless Claude session (claude -p over
  Streamable HTTP as teacher1): whoami → create_course → enrol_student →
  publish_course with visible tool calls. State in the caption that it's a
  rendered transcript of a real session, and that the panels are rendered
  live server responses (not a specific client's UI).
- Regenerate any time: `scripts/screenshots/phase4_rbac_shots.mjs` +
  `phase4_render_session.mjs` (real transcript in, PNG out).

## Interview-question angles

- "How would you do multi-tenant auth in MCP before implementing full OAuth?"
- "Where should authorization live: tool list, tool body, or backend?" (answer: all three, different jobs)
- "Why is deriving permissions from role names an anti-pattern?"
- "What changes between stdio and HTTP transports besides the socket?" (identity model)
