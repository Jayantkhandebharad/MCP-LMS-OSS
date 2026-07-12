# Phase 1 — Moodle setup & seed (COMPLETE, fully scripted)

Everything is reproducible from scratch — no UI clicking:

```bash
cd docker
cp .env.example .env            # edit passwords (NO SPACES in MOODLE_SITENAME)
docker compose up -d            # first boot auto-installs Moodle (~2-3 min)
# wait until: curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login/index.php  → 200

docker compose cp seed/seed_phase1.php moodle:/tmp/
docker compose exec -T moodle php /tmp/seed_phase1.php          # prints API tokens → docker/.env
docker compose cp seed/seed_phase1_content.php moodle:/tmp/
docker compose exec -T moodle php /tmp/seed_phase1_content.php
```

Moodle 5.2.1 at http://localhost:8080 — admin creds in `docker/.env`.

## What the seed creates

| Thing | Details |
|---|---|
| Web services | enabled, REST protocol, `webservice/rest:use` for authenticated users |
| External service | `mcp_service` with 29 functions (courses, enrol, users, quiz, pages, grades, completion) |
| Users | `student1` / `Student1!pass`, `teacher1` / `Teacher1!pass` (local dev only) |
| Courses | `INTRO-MCP` (Intro to MCP, 3 named topics), `DOCKER-101` (Docker Fundamentals) |
| Enrolments | student1 → both courses (student); teacher1 → INTRO-MCP (editingteacher) |
| Content | 2 page activities with real MCP teaching material (sections 1–2) |
| Quiz | "MCP Basics Quiz", 3 MCQs weighted **1 / 2 / 3 marks** (grade scale 6), unlimited attempts |
| Tokens | admin / student1 / teacher1, appended to `docker/.env` (gitignored) |

## Smoke test

```bash
source docker/.env 2>/dev/null || true   # or read tokens from docker/.env
curl -s "http://localhost:8080/webservice/rest/server.php?wstoken=$MOODLE_TOKEN_STUDENT1&wsfunction=core_webservice_get_site_info&moodlewsrestformat=json" | jq '{sitename, username}'
```

Verified working: `core_webservice_get_site_info`, `core_enrol_get_users_courses`,
`core_course_get_contents`, `mod_quiz_get_quizzes_by_courses` — all as student1.

## Gotchas hit (full write-ups in `docs/briefs/phase-3-building-an-mcp-server.md`)

1. bitnami/moodle paywalled → erseco/alpine-moodle
2. Spaces in MOODLE_SITENAME break first-boot install (unquoted arg)
3. Web Services API has NO create-activity functions → internal-API seed script
4. Moodle 5.x: question banks are qbank module instances; `question_make_default_categories()` crashes
5. `quiz_update_sumgrades()` removed → grade_calculator class
6. Moodle 5.2 webroot is `/var/www/html/public/`
