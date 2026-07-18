"""Phase 5 e2e: the MCP authorization spec against a real Keycloak.

Requires the Docker lab (Moodle on :8080, Keycloak on :8081) and the seeded
tokens in docker/.env. The server runs in Act 2 (MOODLE_MCP_AUTH=oauth).
"""

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

REPO_ROOT = Path(__file__).resolve().parents[2]
PORT = 8002
URL = f"http://127.0.0.1:{PORT}/mcp"
KEYCLOAK = "http://localhost:8081/realms/mcp-lms"


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{KEYCLOAK}/.well-known/openid-configuration", timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _keycloak_up(), reason="Keycloak not running")


def _jwt(username: str, password: str, client_id: str = "lab-cli", scope: str = "openid lms:write") -> str:
    r = httpx.post(
        f"{KEYCLOAK}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": client_id,
              "username": username, "password": password, "scope": scope},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def oauth_server():
    proc = subprocess.Popen(
        ["uv", "run", "python", "-c",
         f"from moodle_mcp.server import mcp; mcp.settings.port = {PORT}; "
         "mcp.run(transport='streamable-http')"],
        cwd=REPO_ROOT / "mcp_server",
        env={**os.environ, "MOODLE_MCP_AUTH": "oauth",
             "MCP_RESOURCE_URL": "http://127.0.0.1:8000/mcp"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


def test_unauthenticated_gets_401_with_discovery_pointer(oauth_server):
    """RFC 9728: the 401 challenge must tell the client where the metadata is."""
    r = httpx.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                   headers={"accept": "application/json, text/event-stream"})
    assert r.status_code == 401
    assert "resource_metadata" in r.headers["www-authenticate"]


def test_protected_resource_metadata_document(oauth_server):
    r = httpx.get(f"http://127.0.0.1:{PORT}/.well-known/oauth-protected-resource/mcp")
    doc = r.json()
    assert doc["authorization_servers"] == [KEYCLOAK]
    assert "lms:read" in doc["scopes_supported"]


def test_garbage_token_rejected(oauth_server):
    r = httpx.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                   headers={"accept": "application/json, text/event-stream",
                            "authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_wrong_audience_token_rejected(oauth_server):
    """RFC 8707 resource binding: a VALID realm token minted for another
    service must not work here — this is the anti-confused-deputy property."""
    token = _jwt("student1", "Student1!pass", client_id="other-service-cli", scope="openid")
    r = httpx.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                   headers={"accept": "application/json, text/event-stream",
                            "authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def _session_tools_and_whoami(token: str):
    http = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30)
    async with streamable_http_client(URL, http_client=http) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            who = (await session.call_tool("whoami", {})).content[0].text
            tools = {t.name for t in (await session.list_tools()).tools}
            return who, tools


async def test_student_jwt_maps_to_moodle_identity(oauth_server):
    who, tools = await _session_tools_and_whoami(_jwt("student1", "Student1!pass"))
    assert "Sam Student" in who
    assert "create_course" not in tools and len(tools) == 10


async def test_teacher_jwt_gets_creator_tools(oauth_server):
    """OAuth authenticates; Moodle capabilities still authorize — the RBAC
    layer from Phase 4 composes unchanged with Act 2 auth."""
    who, tools = await _session_tools_and_whoami(_jwt("teacher1", "Teacher1!pass"))
    assert "Tina Teacher" in who
    assert "create_course" in tools and len(tools) == 14
