/**
 * Phase 5 "connected, no token" shot: the payoff of the whole auth series.
 * Renders the add-command (which carries NO secret) beside the authenticated
 * result captured from a real OAuth session (/tmp/oauth-connected.json).
 *
 *   node phase5_connected_shot.mjs
 */
import puppeteer from 'puppeteer-core'
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(join(here, '../../docs/screenshots'))
const data = JSON.parse(readFileSync('/tmp/oauth-connected.json', 'utf8'))
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const who = esc(data.whoami).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d1117; font-family:-apple-system,'Segoe UI',sans-serif; padding:34px; }
  .frame { max-width:860px; margin:0 auto; }
  h1 { color:#e6edf3; font-size:18px; margin-bottom:4px; }
  .sub { color:#7d8590; font-size:13px; margin-bottom:20px; }
  .term { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:16px 18px; font-family:ui-monospace,'SF Mono',monospace; font-size:13px; line-height:1.7; }
  .prompt { color:#7d8590; }
  .cmd { color:#e6edf3; }
  .note { color:#3fb950; }
  .out { color:#8b949e; }
  .badge { display:inline-block; background:rgba(63,185,80,.15); color:#3fb950; font-size:11px; padding:2px 9px; border-radius:10px; margin-left:6px; }
  .callout { margin-top:16px; background:rgba(56,139,253,.08); border:1px solid rgba(56,139,253,.3); border-radius:8px; padding:12px 16px; color:#adbac7; font-size:13px; }
  .callout strong { color:#79c0ff; }
</style></head><body>
  <div class="frame">
    <h1>Connected with zero secrets in the config</h1>
    <div class="sub">The client discovered the identity provider, registered itself, and the user logged in — no token, client id, or password anywhere in the setup.</div>
    <div class="term">
      <div><span class="prompt">$ </span><span class="cmd">claude mcp add --transport http moodle-oauth http://127.0.0.1:8000/mcp</span></div>
      <div class="out">Added HTTP MCP server moodle-oauth <span class="note"># note: no --header, no token</span></div>
      <div style="height:10px"></div>
      <div class="out">/mcp → moodle-oauth → Authenticate → (browser: Keycloak login + consent)</div>
      <div class="out">moodle-oauth<span class="badge">✓ Connected</span></div>
      <div style="height:10px"></div>
      <div><span class="prompt">▸ </span><span class="cmd">whoami</span></div>
      <div class="out">⎿ ${who}</div>
      <div class="out">   ${data.tools.length} tools available (learner set): ${esc(data.tools.slice(0, 6).join(', '))}…</div>
    </div>
    <div class="callout">
      <strong>Contrast with Act 1 (Blog #2):</strong> there, the same command needed
      <code>--header "Authorization: Bearer &lt;a-real-Moodle-token&gt;"</code> — a long-lived
      secret pasted by hand. Here the client obtains a short-lived, audience-bound token on
      its own, after the user consents. That is the whole point of the MCP authorization spec.
    </div>
  </div>
</body></html>`

const tmp = resolve(join(outDir, '.p5.html'))
writeFileSync(tmp, html)
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new',
})
const page = await browser.newPage()
await page.setViewport({ width: 940, height: 100, deviceScaleFactor: 2 })
await page.goto(`file://${tmp}`)
const h = await page.evaluate(() => document.body.scrollHeight)
await page.setViewport({ width: 940, height: h, deviceScaleFactor: 2 })
await page.screenshot({ path: join(outDir, 'phase5-oauth-connected.png') })
await browser.close()
unlinkSync(tmp)
console.log('[shot] phase5-oauth-connected.png')
