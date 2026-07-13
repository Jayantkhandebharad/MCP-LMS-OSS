# Moodle Web Services REST API — cheat-sheet (Phase 2)

Everything learned by hand against Moodle 5.2.1 with the three seeded tokens.
This is the blueprint for the Phase 3 MCP tools.

## The basics

One endpoint, everything is a "function":

```
POST http://localhost:8080/webservice/rest/server.php
  wstoken=<token>
  wsfunction=<function_name>
  moodlewsrestformat=json
  ...function params
```

- GET and POST both work; use POST (tokens in GET URLs leak into logs).
- **HTTP status is always 200** — even for errors. You must check the body.
- Arrays are PHP-style bracketed params: `courseids[0]=2`, `courses[0][fullname]=X`.
- Tokens map to a **user**, and every call executes as that user with their
  permissions — this is the Act 1 auth model, and Moodle enforcing it
  server-side is our RBAC backstop.

## Error shape (uniform, minimal)

```json
{"exception": "...", "errorcode": "...", "message": "..."}
```

| Situation | errorcode | Notes |
|---|---|---|
| Bad/unknown token | `invalidtoken` | |
| Function not whitelisted in the token's service | `accessexception` | Same error whether the function exists or not — no information leak |
| Missing/malformed param | `invalidparameter` | Message rarely says *which* param — MCP tools must validate before calling |
| No capability (e.g. student creates course) | `nopermissions` | Message includes the human-readable capability, e.g. "(Create courses)" |
| Student asks for others' grades | `nopermissiontoviewgrades` | |
| New attempt while one is open | `attemptstillinprogress` | Resume instead — see quiz lifecycle |

## Permission findings (verified per role)

| Call | student1 | teacher1 | admin |
|---|---|---|---|
| `core_webservice_get_site_info` | ✅ | ✅ | ✅ |
| `core_enrol_get_users_courses` | ✅ own | ✅ own | ✅ |
| `core_course_get_contents` | ✅ enrolled courses | ✅ | ✅ |
| `core_course_create_courses` | ❌ nopermissions | **❌ nopermissions** | ✅ |
| `gradereport_user_get_grade_items` (no userid) | ❌ "view grades of other users" | ✅ all students | ✅ |
| `gradereport_user_get_grade_items&userid=<own>` | ✅ | ✅ | ✅ |

**The big one: `editingteacher` cannot create courses.** Moodle roles are
*contextual* — editingteacher exists inside a course; creating courses is a
category/system capability (`coursecreator` or `manager` role). For Phase 4's
`create_course` tool we must either grant teacher1 `coursecreator` in the
category, or scope the Creator tool list to what editingteacher can truly do
(add content to existing courses) and document the difference. Either way:
**derive the tool list from actual capabilities, not from role names.**

## Quiz attempt lifecycle (the messy crown jewel)

Working demo: [`notes/scripts/quiz_attempt_demo.py`](scripts/quiz_attempt_demo.py) — full cycle, perfect 6/6.

```
mod_quiz_start_attempt        quizid=1
  └─ returns attempt {id, layout: "1,0,2,0,3,0"}   ← slots separated by 0 = page breaks
mod_quiz_get_attempt_data     attemptid, page=N
  └─ returns questions[].html — RENDERED BROWSER HTML, not data!
mod_quiz_process_attempt      attemptid, finishattempt=1, data[i][name], data[i][value]
mod_quiz_get_attempt_review   attemptid
  └─ per-question state/mark + total grade
```

Gotchas, all verified:

1. **Answers require parsing HTML.** The API returns each question as the
   rendered form. You must extract `q{attemptid}:{slot}_answer` radio names and
   their values from HTML. There is no structured "options" array.
2. **Options are shuffled per attempt** — radio value 2 might be "Model Context
   Protocol" this attempt and value 0 the next. Match by label text, never by index.
3. **`sequencecheck` hidden fields must be submitted back** with each answer
   (optimistic concurrency); omitting them fails the submission.
4. **One in-progress attempt per user.** `start_attempt` throws
   `attemptstillinprogress`; fetch it with `mod_quiz_get_user_attempts&status=unfinished`
   and resume. Our MCP tool must handle this transparently.
5. `process_attempt` wants answers as indexed name/value pairs:
   `data[0][name]=q4:1_answer&data[0][value]=2&data[1][name]=q4:1_:sequencecheck...`

## Grades

- `gradereport_user_get_grade_items&courseid=2&userid=<own id>` — students MUST
  pass their own userid; omitting it means "all users" and 403s for students.
  Get own id from `core_webservice_get_site_info` (`userid` field).
- Returns `gradeitems[]` with `itemname`, `gradeformatted`, `percentageformatted`;
  last item is the course total (`itemname: null`).

## Misc observations

- `core_course_get_contents` returns pages' content inline only if
  `mod_page_get_pages_by_courses` — course_contents gives file URLs instead;
  fetch page content via the mod_page function (returns `content` HTML directly).
- Site info (`core_webservice_get_site_info`) returns the caller's identity,
  their userid, and the function list their token can call.
  **Phase 4 correction:** that function list is SERVICE-scoped, not user-scoped —
  every token in `mcp_service` gets the identical 29 functions, so it's useless
  for role gating. The real capability signal is
  `core_course_get_user_administration_options` (per-course booleans like
  `update`), which differs per user. See `docs/briefs/phase-4-rbac-in-mcp.md`.
- `core_course_edit_section` is deprecated (gone in Moodle 6.0) —
  use `core_courseformat_update_course` instead. Noted for creator tools.
- Web service create/delete functions exist for courses+users but not activities
  (no create-quiz/page) — already documented in Phase 1 gotchas.

## Function inventory (our `mcp_service`, 29 functions)

Learner-tool candidates: `core_webservice_get_site_info`,
`core_enrol_get_users_courses`, `core_course_get_contents`,
`core_course_search_courses`, `mod_page_get_pages_by_courses`,
`mod_quiz_get_quizzes_by_courses`, `mod_quiz_start_attempt`,
`mod_quiz_get_attempt_data`, `mod_quiz_process_attempt`,
`mod_quiz_get_attempt_review`, `mod_quiz_get_user_attempts`,
`mod_quiz_get_user_best_grade`, `gradereport_user_get_grade_items`,
`core_completion_get_activities_completion_status`.

Creator-tool candidates: `core_course_create_courses`,
`core_user_create_users`, `enrol_manual_enrol_users`,
`core_course_get_categories`, `gradereport_overview_get_course_grades`
(+ the capability caveat above).
