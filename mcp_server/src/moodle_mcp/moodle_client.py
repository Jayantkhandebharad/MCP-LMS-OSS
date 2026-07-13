"""Thin async wrapper around Moodle's Web Services REST API.

Everything ugly about the API is contained here so the MCP tools stay clean:
- the single-endpoint, function-name-in-a-param calling convention
- PHP-style bracketed array encoding (courseids[0]=2)
- errors arriving as HTTP 200 with an "exception" body
"""

from __future__ import annotations

from typing import Any

import httpx

WS_PATH = "/webservice/rest/server.php"


class MoodleAPIError(Exception):
    """A Moodle web-service error (always delivered as HTTP 200 + exception body)."""

    def __init__(self, errorcode: str, message: str):
        self.errorcode = errorcode
        self.message = message
        super().__init__(f"{errorcode}: {message}")


def _flatten(params: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Encode nested structures the way PHP expects them.

    {"courseids": [2, 3]}            -> {"courseids[0]": "2", "courseids[1]": "3"}
    {"courses": [{"fullname": "X"}]} -> {"courses[0][fullname]": "X"}
    """
    flat: dict[str, str] = {}
    for key, value in params.items():
        name = f"{prefix}[{key}]" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, name))
        elif isinstance(value, (list, tuple)):
            flat.update(_flatten({str(i): v for i, v in enumerate(value)}, name))
        elif isinstance(value, bool):
            flat[name] = "1" if value else "0"
        elif value is not None:
            flat[name] = str(value)
    return flat


class MoodleClient:
    """One instance per Moodle user identity (token = user)."""

    def __init__(self, base_url: str, token: str, timeout: float = 30.0):
        self._token = token
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._site_info: dict[str, Any] | None = None
        self._can_manage: bool | None = None

    async def close(self) -> None:
        await self._http.aclose()

    async def call(self, wsfunction: str, **params: Any) -> Any:
        """Call one web-service function and return decoded JSON.

        Raises MoodleAPIError for API-level failures and httpx errors for
        transport-level ones.
        """
        data = {
            "wstoken": self._token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
            **_flatten(params),
        }
        response = await self._http.post(WS_PATH, data=data)
        response.raise_for_status()  # transport errors only; API errors are 200s
        payload = response.json()
        if isinstance(payload, dict) and "exception" in payload:
            raise MoodleAPIError(payload.get("errorcode", "unknown"), payload.get("message", ""))
        return payload

    async def site_info(self) -> dict[str, Any]:
        """Who am I + what can I call. Cached: identity is fixed per token."""
        if self._site_info is None:
            self._site_info = await self.call("core_webservice_get_site_info")
        return self._site_info

    async def my_userid(self) -> int:
        return (await self.site_info())["userid"]

    async def my_courses(self) -> list[dict[str, Any]]:
        """Courses the token's user is enrolled in."""
        return await self.call("core_enrol_get_users_courses", userid=await self.my_userid())

    async def course_contents(self, courseid: int) -> list[dict[str, Any]]:
        """Sections and modules of one course."""
        return await self.call("core_course_get_contents", courseid=courseid)

    async def pages_in_course(self, courseid: int) -> list[dict[str, Any]]:
        """Page activities with their full HTML content."""
        result = await self.call("mod_page_get_pages_by_courses", courseids=[courseid])
        return result["pages"]

    async def quizzes_in_course(self, courseid: int) -> list[dict[str, Any]]:
        result = await self.call("mod_quiz_get_quizzes_by_courses", courseids=[courseid])
        return result["quizzes"]

    async def quiz_attempts(self, quizid: int, status: str = "all") -> list[dict[str, Any]]:
        result = await self.call("mod_quiz_get_user_attempts", quizid=quizid, status=status)
        return result["attempts"]

    async def start_or_resume_attempt(self, quizid: int) -> dict[str, Any]:
        """Start a new attempt, or transparently resume the in-progress one.

        Moodle allows only one open attempt per user (errorcode
        attemptstillinprogress) — an LLM shouldn't have to know that.
        """
        try:
            return (await self.call("mod_quiz_start_attempt", quizid=quizid))["attempt"]
        except MoodleAPIError as e:
            if e.errorcode != "attemptstillinprogress":
                raise
            unfinished = await self.quiz_attempts(quizid, status="unfinished")
            return unfinished[-1]

    async def attempt_pages(self, attempt: dict[str, Any]) -> list[dict[str, Any]]:
        """All raw question blocks of an attempt, across its pages.

        The layout string "1,0,2,0,3,0" lists slots with 0 as page separators.
        """
        page_count = attempt["layout"].count("0") or 1
        questions: list[dict[str, Any]] = []
        for page in range(page_count):
            data = await self.call(
                "mod_quiz_get_attempt_data", attemptid=attempt["id"], page=page
            )
            questions.extend(data["questions"])
        return questions

    async def finish_attempt(self, attemptid: int, fields: dict[str, str]) -> str:
        """Submit answer form fields and finish the attempt. Returns final state."""
        data = [{"name": k, "value": v} for k, v in fields.items()]
        result = await self.call(
            "mod_quiz_process_attempt", attemptid=attemptid, finishattempt=1, data=data
        )
        return result["state"]

    async def attempt_review(self, attemptid: int) -> dict[str, Any]:
        return await self.call("mod_quiz_get_attempt_review", attemptid=attemptid)

    async def my_grades(self, courseid: int) -> list[dict[str, Any]]:
        """Grade items for the current user in one course.

        Students MUST pass their own userid explicitly — omitting it means
        "all users" and fails with nopermissions (cheat-sheet finding).
        """
        result = await self.call(
            "gradereport_user_get_grade_items",
            courseid=courseid,
            userid=await self.my_userid(),
        )
        return result["usergrades"][0]["gradeitems"]

    async def my_completion(self, courseid: int) -> list[dict[str, Any]]:
        result = await self.call(
            "core_completion_get_activities_completion_status",
            courseid=courseid,
            userid=await self.my_userid(),
        )
        return result["statuses"]

    async def search_courses(self, query: str) -> list[dict[str, Any]]:
        result = await self.call(
            "core_course_search_courses", criterianame="search", criteriavalue=query
        )
        return result["courses"]

    async def can_manage_courses(self) -> bool:
        """Is this identity a course manager (capability-derived, cached)?

        True if the user is a site admin OR Moodle grants them the `update`
        administration option in any of their courses. Deliberately NOT based
        on role names — Moodle roles are contextual (an editingteacher can't
        create courses; a coursecreator might not teach any).
        """
        if self._can_manage is None:
            info = await self.site_info()
            if info.get("userissiteadmin"):
                self._can_manage = True
            else:
                courses = await self.my_courses()
                if not courses:
                    self._can_manage = False
                else:
                    result = await self.call(
                        "core_course_get_user_administration_options",
                        courseids=[c["id"] for c in courses],
                    )
                    self._can_manage = any(
                        o["name"] == "update" and o["available"]
                        for c in result["courses"]
                        for o in c["options"]
                    )
        return self._can_manage
