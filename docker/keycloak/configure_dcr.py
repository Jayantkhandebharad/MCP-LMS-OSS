#!/usr/bin/env python3
"""Allow anonymous Dynamic Client Registration on the mcp-lms realm (LAB ONLY).

    python3 docker/keycloak/configure_dcr.py

Keycloak guards anonymous DCR with client-registration policies. The
"Trusted Hosts" policy requires the registering host to be resolvable and
trusted — impossible from the Docker host (Keycloak sees the gateway IP),
so for the lab we DELETE that policy from the anonymous set. We keep the
consent-required policy: dynamically registered clients must show the user
a consent screen — which is exactly what the MCP auth spec wants anyway.

Production note (also in the blog): you'd keep trusted hosts, or require
initial access tokens instead of anonymous DCR.

Stdlib-only on purpose (no venv needed). Reads admin creds from docker/.env.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://localhost:8081"
POLICY_TYPE = "org.keycloak.services.clientregistration.policy.ClientRegistrationPolicy"


def env(name: str) -> str:
    for line in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{name} not found in docker/.env")


def call(method: str, path: str, token: str | None = None, form: dict | None = None):
    req = urllib.request.Request(
        f"{BASE}{path}",
        method=method,
        data=urllib.parse.urlencode(form).encode() if form else None,
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        body = r.read()
        return json.loads(body) if body else None


admin_token = call(
    "POST",
    "/realms/master/protocol/openid-connect/token",
    form={
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": env("KC_ADMIN_USER"),
        "password": env("KC_ADMIN_PASS"),
    },
)["access_token"]

components = call(
    "GET", f"/admin/realms/mcp-lms/components?type={urllib.parse.quote(POLICY_TYPE)}", admin_token
)

removed = 0
for c in components:
    if c.get("subType") == "anonymous" and c.get("providerId") == "trusted-hosts":
        call("DELETE", f"/admin/realms/mcp-lms/components/{c['id']}", admin_token)
        print(f"[ok] removed anonymous policy: {c['name']} ({c['providerId']})")
        removed += 1

if not removed:
    print("[skip] no anonymous trusted-hosts policy present (already removed)")

kept = [c["providerId"] for c in components if c.get("subType") == "anonymous"
        and c.get("providerId") != "trusted-hosts"]
print(f"[ok] anonymous DCR policies kept: {', '.join(kept)}")
print("=== DCR configured ===")
