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
