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
- **(2026-07-18, DCR day) Keycloak's anonymous-DCR "Trusted Hosts" policy can
  never pass from a Docker host** — Keycloak sees the gateway IP, not you.
  Lab fix: `docker/keycloak/configure_dcr.py` deletes that one policy, KEEPS
  consent-required (dynamically registered clients must show a consent screen —
  exactly what MCP wants) and max-clients etc. Production note: initial access
  tokens instead of anonymous DCR.
- **Keycloak login cookies are `Secure; SameSite=None` even over plain http.**
  Real browsers send them anyway (localhost = secure context); Python's
  http.cookiejar refuses on two separate grounds (secure-over-http + RFC 2965
  Version=1), yielding Keycloak's cryptic "Restart login cookie not found".
  Our headless test carries cookies by hand (`_Browser` in test_dcr_flow.py).
  GREAT sidebar: "why your OAuth test fails but your browser works".
- Keycloak serves consent as a *redirect* to a required-action page
  (`execution=OAUTH_GRANT`), not inline after login — headless flows need a
  tiny redirect state machine. And the consent form's action is relative.

## The bug that only a REAL client found (2026-07-19) — great war story

The headless test passed, then Claude Code's **Authenticate** button failed three
different ways in a row. Each failure taught something the test had faked past:

1. **"Policy 'Allowed Client Scopes' rejected request ... not permitted to use
   specified clientScope"** — Keycloak's anonymous DCR is guarded by policies. Our
   realm's `defaultOptionalClientScopes` had *replaced* Keycloak's built-ins,
   dropping `offline_access` that real clients request for refresh tokens; and the
   "Allowed Client Scopes" policy (internal id `allowed-client-templates` — a fossil
   name!) only permits the realm's default scope list. Fix: restore built-in
   optionals + have `configure_dcr.py` remove that policy too.
2. **`invalid_scope: lms:read offline_access` at the authorization step** — the real
   root cause, and the important lesson. **Keycloak assigns a DCR client only the
   scopes it requests**, and a generic MCP client only knows the scopes we advertise
   in Protected Resource Metadata. Our audience + identity mappers lived on a
   separate `mcp-resource` scope the client never asked for → its token had no
   audience and no username. The test had passed only because it registered with NO
   scope field, silently getting the realm defaults — a fidelity gap between test and
   reality. Fix: **move the audience + username + email mappers onto `lms:read`**, the
   one scope the client always requests. Everything the server needs now rides on it.
3. **`Offline tokens not allowed for the user or client`** — our partial realm import
   created users with ZERO role mappings, so they lacked the `offline_access` realm
   role (normally granted via the `default-roles-<realm>` composite). Refresh-token
   issuance failed. Fix: `"realmRoles": ["default-roles-mcp-lms"]` on each user.

Meta-lesson for the post: **a headless test that constructs the "ideal" request can
pass while every real client fails.** The fix made the test register exactly as Claude
Code does (only PRM-advertised scopes) so the gap can't reopen.

## The proof (write the post around this test)

`tests/test_dcr_flow.py::test_full_flow_from_zero` — a "client" born with
nothing but the server URL: 401 → PRM → OIDC discovery → **anonymous DCR**
(201, fresh client_id) → auth-code + PKCE through Keycloak's REAL login and
consent forms as student1 → code exchange → audience-bound JWT → MCP session
says "You are Sam Student" with learner tools only. Zero manual provisioning.
The post can walk this test top to bottom — it IS the spec, executable.

## Code moments (RepoFile embeds)

- `mcp_server/src/moodle_mcp/oauth.py` — the whole verifier
- `mcp_server/src/moodle_mcp/auth.py` — both acts side by side, identity map
- `docker/keycloak/mcp-lms-realm.json` — IdP as code (audience mapper!)
- `mcp_server/tests/test_oauth.py` — the spec as executable assertions
- `mcp_server/src/moodle_mcp/server.py` — `_auth_config()`: the 20 lines that turn on Act 2

## Still to do in Phase 5 (before the post is written)

- [x] DCR enabled (`configure_dcr.py`) — anonymous registration works, consent kept
- [x] Full flow proven headless (`test_dcr_flow.py::test_full_flow_from_zero`)
- [x] **Screenshots DONE** — all three in docs/screenshots/, script-generated
      from the REAL Keycloak flow (not mockups):
      - `phase5-kc-login.png` — the actual Keycloak login page (MCP Learning Lab realm)
      - `phase5-kc-consent.png` — the consent screen: "Grant Access to Claude Code",
        scopes Offline Access + lms:read, Yes/No. THE flagship visual.
      - `phase5-oauth-connected.png` — the payoff: `claude mcp add` with NO token,
        connected, whoami=Sam Student, + the Act-1-vs-Act-2 contrast callout
      Regenerate: `phase5_oauth_shots.mjs` + `phase5_connected_shot.mjs`.
      (An interactive Claude Code capture of the real /mcp panel is a nice-to-have
      the user can add, but the authentic Keycloak pages above are the essential set.)
- [ ] Decided: Moodle SSO via Keycloak OIDC → DEFERRED to a blog sidebar
      (identity already unified by the username mapping; SSO is cosmetic here)
- [ ] Diagrams: the full flow sequence (client ⇄ server ⇄ Keycloak ⇄ user), and
      the confused-deputy "before/after" pair.

## Interview-question angles

- "Walk me through what happens when an MCP client connects to a protected server." (401 → PRM → DCR → PKCE → aud-bound JWT)
- "Why is token passthrough forbidden in the MCP spec?" (confused deputy, audience laundering, consent)
- "How do you bind a token to one resource server?" (RFC 8707 / aud + verifier check)
- "Access token vs the backend's own credentials — who holds what?"
- "Why validate via JWKS offline instead of introspection?" (latency/availability vs revocation immediacy — know the tradeoff)
