# Brief: MCP Auth, Done Right  (Phase 5 → Blog #3, THE FLAGSHIP)

> Status: **collecting** (started 2026-07-18). Post target:
> `portfolio/src/content/blog/mcp/mcp-auth-done-right.tsx`.
> Same audience bar as always — but this post can go deeper: it's the series
> centerpiece and the one interviewers will probe hardest.

## One-line thesis

The reader can explain how a real MCP OAuth 2.1 flow works end to end —
discovery, audience-bound tokens, scopes, DCR — and articulate WHY token
passthrough is forbidden (confused deputy), using our working Keycloak setup
as the running example.

## The two-act contrast (the series' narrative payoff)

Act 1 (Blog #2): bearer = a Moodle token the admin minted by hand. Works, but:
no consent, no expiry, no scopes, tokens smell like passwords, and every
client must be handed one out-of-band.
Act 2 (this post): bearer = a Keycloak-issued JWT. The client discovered the
IdP itself, the user logged in + consented, the token expires in an hour, is
audience-bound to OUR server only, and carries scopes. Same tools, same RBAC —
only `auth.py`/`oauth.py` changed (we predicted this in the Act-1 docstring;
receipts in git history).

## The spec walkthrough (all VERIFIED live, use real transcripts)

1. Client hits the server with no token → **401** with
   `WWW-Authenticate: Bearer ... resource_metadata="…/.well-known/oauth-protected-resource/mcp"`.
2. Client fetches **Protected Resource Metadata (RFC 9728)** → learns the
   authorization server is our Keycloak realm + which scopes exist.
3. Client registers itself (**Dynamic Client Registration**) / runs
   **auth-code + PKCE**; user logs in at Keycloak and consents.
4. Token comes back **audience-bound (RFC 8707)**: `aud = http://127.0.0.1:8000/mcp`,
   stamped by a Keycloak client-scope audience mapper.
5. Server validates OFFLINE via the realm's **JWKS** (signature, exp, iss, aud,
   required scope lms:read) — `oauth.py`, ~60 lines with PyJWT.
6. Identity mapping: `preferred_username` → that user's server-held Moodle
   token (`auth.py`). **The JWT never reaches Moodle. No passthrough.**

## Confused deputy section (the interview centerpiece)

- Concrete story: if our server FORWARDED bearer tokens to Moodle, any token
  that "looks right" gets Moodle authority the caller never consented to; and a
  token stolen from service X could be replayed against us. Our design kills
  both: (a) wrong-audience tokens are rejected at the door — TEST EXISTS
  (`test_wrong_audience_token_rejected`: a valid realm token minted for
  `other-service-cli` bounces with 401), (b) Moodle credentials never leave the
  server process.
- The three-key metaphor: OAuth token = signed visitor badge for THIS building;
  Moodle token = master key kept by the receptionist; visitor never holds it.

## Real issues we hit (2026-07-18)

- **Keycloak 26 access tokens arrived with ZERO identity claims** — no sub, no
  preferred_username, nothing but iss/aud/scope. Realm-import ordering left the
  built-in profile/email scopes unattached to our client. Fix worth teaching:
  put username/email protocol mappers ON our own `mcp-resource` client scope, so
  identity always travels with the audience. (Also: decode your tokens at
  jwt.io-style FIRST, assume nothing.)
- **Audience in Keycloak is a mapper, not a checkbox**: RFC 8707 resource
  binding = client scope `mcp-resource` with `oidc-audience-mapper`, set as a
  realm default so every (dynamically registered) client gets it.
- The **SDK does the spec plumbing**: resource-server mode is just
  `FastMCP(token_verifier=…, auth=AuthSettings(issuer_url, resource_server_url,
  required_scopes))` — PRM route + WWW-Authenticate come free. Way less code
  than readers expect (~100 lines total for us).
- **Realm-in-git reproducibility**: `start-dev --import-realm` + JSON in
  `docker/keycloak/`. Import runs only on empty data volume — iterate with
  `docker volume rm docker_kcdata`. The IdP is code, not clicks.
- `lab-cli` password-grant client exists ONLY for curl/pytest (labeled as such
  in the realm); real clients use auth-code + PKCE + DCR.

## Code moments (RepoFile embeds)

- `mcp_server/src/moodle_mcp/oauth.py` — the whole verifier
- `mcp_server/src/moodle_mcp/auth.py` — both acts side by side, identity map
- `docker/keycloak/mcp-lms-realm.json` — IdP as code (audience mapper!)
- `mcp_server/tests/test_oauth.py` — the spec as executable assertions
- `mcp_server/src/moodle_mcp/server.py` — `_auth_config()`: the 20 lines that turn on Act 2

## Still to do in Phase 5 (before the post is written)

- [ ] DCR: relax Keycloak's anonymous client-registration policy (trusted
      hosts) so a real MCP client can self-register
- [ ] The real-client demo: `claude mcp add --transport http` → 401 → browser
      opens Keycloak login as student1 → consent → tools appear. Screenshots:
      Keycloak login page, consent screen, connected client. THE money shots.
- [ ] Decide: Moodle SSO via Keycloak OIDC (plan §5 "same users" box) — stretch
      goal; identity is already unified by username mapping, SSO is cosmetic
      for the demo but completes the architecture diagram. Maybe Blog #3 sidebar.
- [ ] Diagrams: the full flow sequence (client ⇄ server ⇄ Keycloak ⇄ user), and
      the confused-deputy "before/after" pair.

## Interview-question angles

- "Walk me through what happens when an MCP client connects to a protected server." (401 → PRM → DCR → PKCE → aud-bound JWT)
- "Why is token passthrough forbidden in the MCP spec?" (confused deputy, audience laundering, consent)
- "How do you bind a token to one resource server?" (RFC 8707 / aud + verifier check)
- "Access token vs the backend's own credentials — who holds what?"
- "Why validate via JWKS offline instead of introspection?" (latency/availability vs revocation immediacy — know the tradeoff)
