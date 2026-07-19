"""Phase 5 grand finale: the ENTIRE MCP auth flow, headless.

Plays the role of a brand-new MCP client with nothing but the server URL:

    1. hit the server         -> 401 + resource_metadata pointer
    2. fetch PRM              -> discover Keycloak
    3. Dynamic Client Registration -> get a client_id (no pre-provisioning!)
    4. authorization-code + PKCE: submit Keycloak's real login form as
       student1, accept the consent screen
    5. exchange the code for an audience-bound JWT
    6. call the MCP server with it -> "You are Sam Student"

If this passes, any spec-compliant MCP client can onboard with zero manual
setup — which is the entire point of the MCP authorization spec.
"""

import base64
import hashlib
import os
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

REPO_ROOT = Path(__file__).resolve().parents[2]
# This test runs the server at its REAL advertised address: discovery URLs and
# the token audience all say 127.0.0.1:8000, so unlike the other fixtures we
# cannot hide on an alternate port.
PORT = 8000
MCP_URL = f"http://127.0.0.1:{PORT}/mcp"
REDIRECT_URI = "http://127.0.0.1:33418/callback"


def _keycloak_up() -> bool:
    try:
        return httpx.get("http://localhost:8081/realms/mcp-lms/.well-known/openid-configuration",
                         timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _keycloak_up(), reason="Keycloak not running")


@pytest.fixture(scope="module")
def oauth_server():
    proc = subprocess.Popen(
        ["uv", "run", "python", "-c",
         f"from moodle_mcp.server import mcp; mcp.settings.port = {PORT}; "
         "mcp.run(transport='streamable-http')"],
        cwd=REPO_ROOT / "mcp_server",
        env={**os.environ, "MOODLE_MCP_AUTH": "oauth",
             "MCP_RESOURCE_URL": "http://127.0.0.1:8000/mcp"},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail(f"server never opened port {PORT}")
    yield
    proc.terminate()
    proc.wait(timeout=5)


def _form_action(html: str) -> str:
    match = re.search(r'<form[^>]+action="([^"]+)"', html)
    assert match, f"no form found in page: {html[:300]}"
    return match.group(1).replace("&amp;", "&")


class _Browser:
    """A four-line browser: GET/POST with manual cookie carrying.

    Why not a cookie jar? Keycloak sets its login cookies with
    `Secure; SameSite=None; Version=1` even over plain http. Real browsers
    send them anyway (localhost is a secure context); http.cookiejar's
    policy engine refuses on TWO counts (secure-over-http and RFC 2965
    versioning), and you get Keycloak's cryptic "Restart login cookie not
    found". Carrying cookies by hand is honest and obvious."""

    def __init__(self):
        self._client = httpx.Client(follow_redirects=False)
        self._cookies: dict[str, str] = {}

    def _do(self, method: str, url: str, **kw) -> httpx.Response:
        headers = {"cookie": "; ".join(f"{k}={v}" for k, v in self._cookies.items())}
        r = self._client.request(method, url, headers=headers, **kw)
        for value in r.headers.get_list("set-cookie"):
            name, _, rest = value.partition("=")
            self._cookies[name.strip()] = rest.split(";", 1)[0]
        return r

    def get(self, url: str, **kw) -> httpx.Response:
        return self._do("GET", url, **kw)

    def post(self, url: str, **kw) -> httpx.Response:
        return self._do("POST", url, **kw)

    def close(self) -> None:
        self._client.close()


async def test_full_flow_from_zero(oauth_server):
    # 1. knock on the door with no credentials
    r = httpx.post(MCP_URL, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                   headers={"accept": "application/json, text/event-stream"})
    assert r.status_code == 401
    prm_url = re.search(r'resource_metadata="([^"]+)"', r.headers["www-authenticate"]).group(1)

    # 2. discovery: PRM -> authorization server -> its OIDC configuration
    prm = httpx.get(prm_url).json()
    issuer = prm["authorization_servers"][0]
    oidc = httpx.get(f"{issuer}/.well-known/openid-configuration").json()

    # 3. Dynamic Client Registration — no admin pre-provisioning.
    # Register the way a REAL client (Claude Code) does: request only the
    # scopes advertised in PRM, plus openid/offline_access. This is the case
    # that broke in practice — Keycloak assigns a DCR client only the scopes
    # it requests, so the audience/identity mappers must ride on lms:read
    # (a scope the client actually asks for), not a separate resource scope.
    advertised = " ".join(["openid", "offline_access", *prm["scopes_supported"]])
    reg = httpx.post(oidc["registration_endpoint"], json={
        "client_name": "pytest MCP client",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
        "scope": advertised,
    })
    assert reg.status_code == 201
    client_id = reg.json()["client_id"]

    # 4. authorization code + PKCE, driving Keycloak's real HTML forms
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    browser = _Browser()
    try:
        r = browser.get(oidc["authorization_endpoint"], params={
            "client_id": client_id, "redirect_uri": REDIRECT_URI,
            "response_type": "code", "scope": "openid lms:read offline_access",
            "code_challenge": challenge, "code_challenge_method": "S256",
            "state": "xyz",
        })
        assert r.status_code == 200, "expected the login page"

        # submit the login form as student1, then walk Keycloak's redirect
        # dance: login -> (required-action: consent screen) -> callback.
        # The consent screen exists because the DCR consent-required policy
        # marks dynamically registered clients consentRequired — by design.
        r = browser.post(urljoin(str(r.url), _form_action(r.text)),
                         data={"username": "student1", "password": "Student1!pass"})
        location = None
        for _ in range(6):
            if r.status_code in (302, 303):
                location = r.headers["location"]
                if location.startswith(REDIRECT_URI):
                    break
                r = browser.get(location)
            elif r.status_code == 200 and ("consent" in r.text.lower() or "OAUTH_GRANT" in r.text):
                r = browser.post(urljoin(str(r.url), _form_action(r.text)), data={"accept": "Yes"})
            else:
                raise AssertionError(f"stuck at {r.status_code}: {r.text[:200]}")
        assert location and location.startswith(REDIRECT_URI), "never reached the callback"
        code = parse_qs(urlparse(location).query)["code"][0]
    finally:
        browser.close()

    # 5. exchange the code (PKCE verifier proves we started the flow)
    token_response = httpx.post(oidc["token_endpoint"], data={
        "grant_type": "authorization_code", "client_id": client_id,
        "code": code, "redirect_uri": REDIRECT_URI, "code_verifier": verifier,
    })
    assert token_response.status_code == 200
    access_token = token_response.json()["access_token"]

    # 6. the token opens the MCP server — as Sam, with learner tools only
    authed = httpx.AsyncClient(headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    async with streamable_http_client(MCP_URL, http_client=authed) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            who = (await session.call_tool("whoami", {})).content[0].text
            assert "Sam Student" in who
            tools = {t.name for t in (await session.list_tools()).tools}
            assert "create_course" not in tools
