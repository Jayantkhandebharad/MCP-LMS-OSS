/**
 * Phase 5 blog screenshots: the REAL Keycloak login + consent pages that an
 * MCP client's OAuth flow drives. Authentic — this registers a client via DCR
 * and navigates the actual authorization endpoint, same as Claude Code does.
 *
 *   node phase5_oauth_shots.mjs      (Keycloak must be up on :8081)
 */
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash, randomBytes } from 'node:crypto'

const here = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(join(here, '../../docs/screenshots'))
mkdirSync(outDir, { recursive: true })

const REALM = 'http://localhost:8081/realms/mcp-lms'
const RESOURCE = 'http://127.0.0.1:8000/mcp'
const REDIRECT = 'http://127.0.0.1:59999/callback'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

// 1. Dynamic Client Registration — exactly what an MCP client does
const reg = await (await fetch(`${REALM}/clients-registrations/openid-connect`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    client_name: 'Claude Code',
    redirect_uris: [REDIRECT],
    grant_types: ['authorization_code', 'refresh_token'],
    token_endpoint_auth_method: 'none',
    scope: 'openid lms:read offline_access',
  }),
})).json()

const verifier = randomBytes(48).toString('base64url')
const challenge = createHash('sha256').update(verifier).digest('base64url')
const authUrl = `${REALM}/protocol/openid-connect/auth?` + new URLSearchParams({
  client_id: reg.client_id, redirect_uri: REDIRECT, response_type: 'code',
  scope: 'openid lms:read offline_access', code_challenge: challenge,
  code_challenge_method: 'S256', state: 'demo', resource: RESOURCE,
})

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' })
const page = await browser.newPage()
await page.setViewport({ width: 1000, height: 720, deviceScaleFactor: 2 })

// 2. the login page
await page.goto(authUrl, { waitUntil: 'networkidle2' })
await page.screenshot({ path: join(outDir, 'phase5-kc-login.png') })
console.log('[shot] phase5-kc-login.png')

// 3. log in -> consent page (a fresh client always prompts for consent)
await page.type('#username', 'student1')
await page.type('#password', 'Student1!pass')
await Promise.all([
  page.waitForNavigation({ waitUntil: 'networkidle2' }),
  page.click('#kc-login'),
])
const url = page.url()
if (url.startsWith(REDIRECT)) {
  console.log('[warn] jumped straight to callback — consent not shown for this client')
} else {
  // Any non-callback page here IS the consent/grant screen.
  await page.screenshot({ path: join(outDir, 'phase5-kc-consent.png') })
  console.log('[shot] phase5-kc-consent.png  (page:', url.split('?')[0], ')')
}

await browser.close()
console.log('done')
