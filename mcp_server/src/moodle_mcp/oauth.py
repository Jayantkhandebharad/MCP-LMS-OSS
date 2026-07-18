"""Act 2 auth: validate real OAuth 2.1 access tokens from Keycloak.

The MCP server is a *resource server* per the MCP authorization spec:
- it advertises Protected Resource Metadata (RFC 9728) so clients can
  discover the authorization server (the SDK mounts that route for us),
- it validates each request's JWT: signature via the realm's JWKS,
  issuer, expiry, and — crucially — the AUDIENCE (RFC 8707 resource
  binding: a token minted for another service must not work here),
- it then maps the authenticated identity to that user's Moodle token.

That last step is the anti-pattern-killer: the OAuth token NEVER reaches
Moodle (no token passthrough). Moodle only ever sees Moodle tokens the
server holds; the OAuth layer decides WHOSE token gets used. See the
Blog #3 brief for the confused-deputy write-up.
"""

from __future__ import annotations

import sys

import anyio
import jwt as pyjwt
from mcp.server.auth.provider import AccessToken, TokenVerifier


class KeycloakTokenVerifier(TokenVerifier):
    """Validates realm-issued JWTs offline via the realm's JWKS."""

    def __init__(self, issuer: str, resource: str):
        self._issuer = issuer.rstrip("/")
        self._resource = resource
        self._jwks = pyjwt.PyJWKClient(
            f"{self._issuer}/protocol/openid-connect/certs", cache_keys=True
        )

    def _decode(self, token: str) -> dict:
        signing_key = self._jwks.get_signing_key_from_jwt(token)  # blocking HTTP
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self._resource,  # reject tokens minted for other resources
            issuer=self._issuer,
            options={"require": ["exp", "iss", "aud"]},
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = await anyio.to_thread.run_sync(self._decode, token)
        except pyjwt.PyJWTError as e:
            print(f"token rejected: {e}", file=sys.stderr)
            return None
        return AccessToken(
            token=token,
            client_id=claims.get("azp", "unknown"),
            scopes=claims.get("scope", "").split(),
            expires_at=claims.get("exp"),
            resource=self._resource,
            subject=claims.get("sub"),
            claims=claims,  # carries preferred_username/email for identity mapping
        )
