# Moodle MCP Server — Project Plan & Decisions

> **Purpose of this file:** Records every decision made during planning so any session — human or Claude — can pick up from here without re-litigating.

## 1. What this project is

A **production-grade MCP (Model Context Protocol) server** that wraps a self-hosted **Moodle LMS**, exposing role-gated tools to any AI client (Claude Desktop, Claude Code, Cursor, ChatGPT, etc.).

**Goals (in priority order):**
1. **Learn MCP deeply** — every primitive, transport, and the auth spec — to the level an interviewer can probe.
2. **Blog series** — one post per phase; the OAuth post is the flagship. Blog lives at jayantkhd.vercel.app.
3. Learn supporting infra along the way: Docker → (later) Kubernetes → (later) GCP.

**Where the blog actually lives:** the posts are written in the **portfolio repo**, NOT here — series registry at `portfolio/src/content/blog.ts` (slug `mcp`), post bodies at `portfolio/src/content/blog/mcp/*.tsx` (all five already scaffolded as "Coming Soon" with titles/summaries/phases, and the series links back to this repo). This repo's job is the *code* plus per-phase **blog briefs** in `docs/briefs/` — raw material (concepts covered, real issues hit, code moments, gotchas) captured while building, then handed to the blog writer. See `docs/briefs/README.md` for the template.

**Non-goals:** building an LMS from scratch, polished UI work, video hosting/transcoding. Moodle provides the platform; 100% of our effort goes into the MCP layer.

## 2. Decisions locked

| Decision | Choice | Why |
|---|---|---|
| Platform | **Wrap existing OSS LMS — Moodle** (not build our own, not Canvas/Open edX/Frappe) | Easiest to self-host in Docker; has courses/topics/MCQ quizzes with per-question weightage, enrollment, and a real role system (Student/Teacher/Manager) out of the box; huge blog audience. Its clunky API is itself blog material ("clean MCP tools over a messy legacy API") |
| MCP SDK | **Python + FastMCP** (official Python SDK) | Matches user's AI-engineering background; pairs with Python tooling; most common in AI blog circles |
| Auth strategy | **Two acts** (see §5) — Moodle web-service token mapping first, full OAuth 2.1 + Keycloak second | Ship something real fast, then cover the actual MCP auth spec; the contrast is itself an interview topic |
| RBAC | **Role-gated tool lists** — students and teachers see *different tools* | The differentiator vs toy MCP servers; Moodle's own permission system is the enforcement backstop |
| Deployment | **Local-first, free**: Docker Compose now; kind/minikube → GKE Autopilot or Cloud Run **later (deferred)** | K8s/GCP is Phase 7; don't touch until MCP + auth are done and blogged |
| Cloud | GCP (over AWS) when we get there | User preference for learning GCP first |
| Repo | Public GitHub repo (`MCP-LMS-OSS`), MIT license for our code | We only ship compose files + MCP server; we don't redistribute Moodle (GPL) itself |

**Watch-out:** the classic `bitnami/moodle` image moved behind Broadcom's paid program (late 2025). Use `moodlehq` images or a maintained community image (e.g. `erseco/alpine-moodle`) — verify at build time.

## 3. Architecture

```
AI client (Claude Desktop / Claude Code / Cursor / any MCP client)
      │  stdio (Phase 3) → Streamable HTTP + OAuth 2.1 bearer token (Phase 4-5)
      ▼
┌──────────────────────────────┐    validates JWT,     ┌──────────────┐
│  MCP Server (Python/FastMCP)  │◄───reads roles/scopes──│   Keycloak   │  Phase 5
│  tools / resources / prompts  │                        │  (OSS IdP)   │
│  role-gated per caller        │                        └──────┬───────┘
└──────────────┬───────────────┘                                │ OIDC SSO
               │ Moodle Web Services (REST)                     ▼
┌──────────────────────────────┐                        ┌──────────────┐
│   Moodle (Docker Compose)     │◄───────login──────────│  same users  │
│   + MariaDB/Postgres          │                        └──────────────┘
└──────────────────────────────┘
```

## 4. Roles → MCP tools

| Role | Tools |
|---|---|
| **Learner** (Moodle: Student) | `list_my_courses`, `get_course_contents`, `get_topic_material`, `search_content`, `get_quiz`, `submit_quiz_answer`, `get_my_grades`, `get_my_progress`, `generate_practice_quiz`*, `explain_concept`* |
| **Creator** (Moodle: Teacher/Manager) | all learner tools **+** `create_course`, `add_topic`, `add_material`, `create_quiz`, `add_quiz_question` (with weightage), `publish_course`, `view_course_analytics` |

\* "Go beyond the course" tools — LLM-powered, candidates for MCP **sampling** (server-initiated LLM calls).

Also expose non-tool primitives (interview coverage):
- **Resources:** `course://{id}`, `course://{id}/topic/{n}`, `quiz://{id}`
- **Prompts:** `quiz_me`, `study_plan`, `explain_like_im_new`

**Key demo:** the tool list itself changes with the authenticated identity — a learner's client never even sees `create_course`.

## 5. Auth story (two acts)

**Act 1 — Token mapping (Phase 4):** Moodle issues per-user *web service tokens*. MCP server accepts a bearer token → maps to a Moodle user → calls Moodle's API *as that user*. Moodle's permission system is the enforcement backstop (a student token physically cannot create a course). Tool list filtered by the caller's Moodle role.

**Act 2 — Full MCP OAuth 2.1 (Phase 5, flagship blog):** Keycloak as IdP; Moodle logs in via Keycloak (OIDC) so identity is unified. MCP server implements the MCP authorization spec:
- **Protected Resource Metadata (RFC 9728)** discovery
- Token validation, scopes, resource indicators (RFC 8707)
- Dynamic Client Registration
- AI client connecting triggers a real OAuth flow (user logs in at Keycloak, consents, client gets scoped token)
- Write up the **confused deputy problem** and **why token passthrough is forbidden**

## 6. Phased plan (each phase = checkpoint + blog post)

| Phase | Work | Output |
|---|---|---|
| **0** | GitHub repo (public, MIT), README skeleton, this file as CLAUDE.md, `.gitignore`, project layout (§7) | Repo live |
| **1** | Moodle via Docker Compose; admin setup; seed 1–2 courses (e.g. "Intro to MCP") with topics + MCQ quiz with weightage; create student + teacher test users; enable Web Services + REST protocol | Working seeded LMS |
| **2** | Explore Moodle Web Services by hand (curl): token auth, `core_course_*`, `mod_quiz_*`, `gradereport_*` | `notes/api-cheatsheet.md` |
| **3** | **MCP server v1** — FastMCP, stdio, single token. Learner tools + resources + prompts. Test with MCP Inspector + Claude Desktop/Code | 📝 **Blog #1: "I built an MCP server for Moodle"** |
| **4** | **Streamable HTTP** transport; multi-user bearer→Moodle-token mapping; **role-gated tools** (teacher tools appear) | 📝 **Blog #2: RBAC in MCP — different tools for different users** |
| **5** | **Keycloak + OAuth 2.1** per MCP spec (§5 Act 2) | 📝 **Blog #3 (flagship): MCP auth done right** |
| **6** | Polish: sampling-powered `generate_practice_quiz`; security hardening pass (tool poisoning, prompt injection, confused deputy) | 📝 **Blog #4: Securing an MCP server** |
| **7** | *(deferred)* Docker → kind → GKE Autopilot/Cloud Run, Helm chart | 📝 Blog #5 |

Everything through Phase 6 runs free on a Mac with Docker Desktop.

## 7. Repo layout

```
MCP-LMS-OSS/
├── CLAUDE.md                    # this file
├── README.md
├── docker/
│   └── docker-compose.yml       # Moodle + DB (+ Keycloak in Phase 5)
├── mcp_server/
│   ├── pyproject.toml           # uv-managed
│   ├── src/moodle_mcp/
│   │   ├── server.py            # FastMCP entrypoint
│   │   ├── moodle_client.py     # thin Moodle Web Services wrapper
│   │   ├── auth.py              # Act 1 token mapping → Act 2 OAuth
│   │   └── tools/
│   │       ├── learner.py
│   │       └── creator.py
│   └── tests/
├── docs/briefs/                 # blog briefs per phase (posts live in portfolio repo)
└── notes/                       # api-cheatsheet.md, decisions, gotchas
```

## 8. Interview-topic coverage map

| Built artifact | Interview topic |
|---|---|
| Tools + resources + prompts | The three MCP primitives, when to use each |
| stdio → Streamable HTTP | Transports; why SSE was deprecated; stateful vs stateless |
| Keycloak + PRM + scopes + DCR | MCP OAuth 2.1 spec end-to-end |
| Role-gated tool lists | AuthN vs AuthZ; per-identity capabilities |
| Token mapping vs passthrough | Confused deputy; why passthrough is forbidden |
| `generate_practice_quiz` via sampling | Server-initiated LLM calls |
| Clean tools over Moodle's clunky API | Tool design / naming / error messages for LLM consumers |
| Security pass | Tool poisoning, prompt injection, least privilege |
| Compose → k8s → GCP (later) | Deployment & portability |

## 9. Conventions

- **Free/local-first:** nothing may require a paid service before Phase 7.
- **Portable:** everything reproducible via `docker compose up` + documented seed steps.
- **Brief as you go:** each blog-bearing phase ends with a brief in `docs/briefs/` — capture real issues and gotchas *the day they happen*; the post itself is written later in the portfolio repo.
- **Python tooling:** `uv` for env/deps; `pytest` for tests.
- **Commits:** small, per-feature; the repo history itself supports the blog narrative.

## 10. Current status

- [x] Planning complete, decisions locked (2026-07-12)
- [x] Phase 0: repo created, layout scaffolded (2026-07-12)
- [x] Phase 1: Moodle 5.2.1 running + fully scripted seed (2026-07-12) — see `notes/phase-1-seed-plan.md`; tokens in `docker/.env`
- [x] Phase 2: API cheat-sheet (2026-07-12) — `notes/api-cheatsheet.md`; key findings: quiz answers require HTML parsing, editingteacher can't create courses (contextual roles!), site_info returns per-token function list (Phase 4 gating)
- [ ] Phase 3: MCP server v1 (stdio) — Blog #1
- [ ] Phase 4: HTTP + RBAC — Blog #2
- [ ] Phase 5: OAuth 2.1 + Keycloak — Blog #3
- [ ] Phase 6: sampling + security — Blog #4
- [ ] Phase 7: k8s + GCP — Blog #5 *(deferred)*
