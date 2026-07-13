/**
 * Phase 4 blog screenshots: the role-gated tool lists, from live responses.
 *
 *   node phase4_rbac_shots.mjs            (server must be running: moodle-mcp --http)
 *
 * Speaks real Streamable HTTP MCP (initialize -> initialized -> tools/list)
 * with student1's and teacher1's bearer tokens, then renders what each
 * caller's client sees. Not a mockup of any specific client UI — the panels
 * are labeled as rendered tools/list responses.
 */
import puppeteer from 'puppeteer-core'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(join(here, '../../docs/screenshots'))
mkdirSync(outDir, { recursive: true })

const env = Object.fromEntries(
  readFileSync(join(here, '../../docker/.env'), 'utf8')
    .split('\n')
    .filter((l) => l.includes('=') && !l.startsWith('#'))
    .map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]),
)

const MCP_URL = 'http://127.0.0.1:8000/mcp'

function parseSSE(text) {
  const line = text.split('\n').find((l) => l.startsWith('data: '))
  return JSON.parse(line ? line.slice(6) : text)
}

async function rpc(token, session, body) {
  const res = await fetch(MCP_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      authorization: `Bearer ${token}`,
      ...(session ? { 'mcp-session-id': session } : {}),
    },
    body: JSON.stringify(body),
  })
  return { res, text: await res.text() }
}

async function toolList(token) {
  const init = await rpc(token, null, {
    jsonrpc: '2.0', id: 1, method: 'initialize',
    params: {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'blog-shot', version: '0' },
    },
  })
  const session = init.res.headers.get('mcp-session-id')
  await rpc(token, session, { jsonrpc: '2.0', method: 'notifications/initialized' })
  const list = await rpc(token, session, { jsonrpc: '2.0', id: 2, method: 'tools/list' })
  return parseSSE(list.text).result.tools.map((t) => ({
    name: t.name,
    readonly: t.annotations?.readOnlyHint === true,
  }))
}

const student = await toolList(env.MOODLE_TOKEN_STUDENT1)
const teacher = await toolList(env.MOODLE_TOKEN_TEACHER1)
console.log(`student1: ${student.length} tools | teacher1: ${teacher.length} tools`)

const studentNames = new Set(student.map((t) => t.name))

function panel(title, subtitle, tools, highlightNew) {
  const rows = tools
    .map((t) => {
      const isNew = highlightNew && !studentNames.has(t.name)
      return `<li class="${isNew ? 'new' : ''}">
        <span class="dot"></span><code>${t.name}</code>
        ${t.readonly ? '<span class="badge ro">read-only</span>' : ''}
        ${isNew ? '<span class="badge creator">creator</span>' : ''}
      </li>`
    })
    .join('')
  return `<div class="panel">
    <div class="head"><span class="who">${title}</span><span class="sub">${subtitle}</span></div>
    <div class="conn">✓ Connected — ${tools.length} tools</div>
    <ul>${rows}</ul>
  </div>`
}

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d1117; font-family:-apple-system,'Segoe UI',sans-serif; padding:36px; }
  h1 { color:#e6edf3; font-size:20px; font-weight:600; margin-bottom:6px; }
  .note { color:#7d8590; font-size:13px; margin-bottom:24px; }
  .wrap { display:flex; gap:24px; }
  .panel { flex:1; background:#161b22; border:1px solid #30363d; border-radius:12px; padding:20px; }
  .head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px; }
  .who { color:#e6edf3; font-size:15px; font-weight:600; }
  .sub { color:#7d8590; font-size:11px; font-family:ui-monospace,monospace; }
  .conn { color:#3fb950; font-size:12px; margin-bottom:14px; }
  ul { list-style:none; }
  li { display:flex; align-items:center; gap:8px; padding:7px 10px; border-radius:6px; }
  li.new { background:rgba(63,185,80,.08); outline:1px solid rgba(63,185,80,.35); margin:2px 0; }
  .dot { width:5px; height:5px; border-radius:50%; background:#7d8590; flex:none; }
  li.new .dot { background:#3fb950; }
  code { color:#e6edf3; font-size:13px; font-family:ui-monospace,'SF Mono',monospace; }
  .badge { font-size:10px; padding:2px 7px; border-radius:10px; margin-left:auto; }
  .ro { background:rgba(56,139,253,.15); color:#79c0ff; }
  .creator { background:rgba(63,185,80,.2); color:#3fb950; margin-left:8px; }
</style></head><body>
  <h1>One MCP server, two callers</h1>
  <div class="note">Live <code style="color:#a5b1bd">tools/list</code> responses from http://127.0.0.1:8000/mcp — only the Authorization header differs.</div>
  <div class="wrap">
    ${panel('student1 (Sam)', 'Authorization: Bearer &lt;student1-token&gt;', student, false)}
    ${panel('teacher1 (Tina)', 'Authorization: Bearer &lt;teacher1-token&gt;', teacher, true)}
  </div>
</body></html>`

const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new',
})

async function shoot(name, pageHtml, width) {
  const tmp = join(outDir, '.phase4.html')
  writeFileSync(tmp, pageHtml)
  const page = await browser.newPage()
  await page.setViewport({ width, height: 100, deviceScaleFactor: 2 })
  await page.goto(`file://${tmp}`)
  const height = await page.evaluate(() => document.body.scrollHeight)
  await page.setViewport({ width, height, deviceScaleFactor: 2 })
  await page.screenshot({ path: join(outDir, name) })
  await page.close()
  console.log('[shot]', name)
  const { unlinkSync } = await import('node:fs')
  unlinkSync(tmp)
}

const solo = (inner) =>
  html.replace(/<div class="wrap">[\s\S]*<\/div>\n<\/body>/, `<div class="wrap">${inner}</div></body>`)

await shoot('phase4-tools-diff.png', html, 1240)
await shoot('phase4-tools-student.png', solo(panel('student1 (Sam)', 'Authorization: Bearer &lt;student1-token&gt;', student, false)), 660)
await shoot('phase4-tools-teacher.png', solo(panel('teacher1 (Tina)', 'Authorization: Bearer &lt;teacher1-token&gt;', teacher, true)), 660)
await browser.close()
