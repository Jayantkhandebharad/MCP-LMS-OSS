/**
 * Render a `claude -p --output-format stream-json` transcript as a chat panel.
 *
 *   node phase4_render_session.mjs <session.jsonl> <out.png> [title]
 *
 * Used for the Blog #2 teacher-workflow demo: the transcript comes from a
 * REAL headless session (real tool calls against the live server) — this
 * script only renders it.
 */
import puppeteer from 'puppeteer-core'
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

const [jsonlPath, outPath, promptArg,
  title = 'Claude Code session — connected as teacher1 over Streamable HTTP'] = process.argv.slice(2)

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>')

const blocks = []
let prompt = promptArg || null
for (const line of readFileSync(jsonlPath, 'utf8').split('\n')) {
  let e
  try { e = JSON.parse(line) } catch { continue }
  if (e.type === 'system' && e.subtype === 'init') continue
  if (e.type === 'user' && typeof e.message?.content === 'string' && !prompt) {
    prompt = e.message.content
  }
  if (e.type === 'assistant') {
    for (const b of e.message.content) {
      if (b.type === 'text' && b.text.trim()) blocks.push({ kind: 'text', text: b.text })
      else if (b.type === 'tool_use' && b.name.startsWith('mcp__moodle__'))
        blocks.push({ kind: 'call', name: b.name.replace('mcp__moodle__', ''), input: JSON.stringify(b.input) })
    }
  }
  if (e.type === 'user') {
    const content = e.message?.content
    if (Array.isArray(content)) {
      for (const b of content) {
        if (b.type === 'tool_result') {
          const raw = Array.isArray(b.content) ? (b.content[0]?.text ?? '') : String(b.content ?? '')
          let text = raw
          try { text = JSON.parse(raw).result } catch {}
          const last = blocks.at(-1)
          if (last?.kind === 'call' && !last.result) last.result = text
        }
      }
    }
  }
}

const rows = blocks.map((b) => {
  if (b.kind === 'text') return `<div class="msg">${md(b.text)}</div>`
  const input = b.input.length > 92 ? b.input.slice(0, 92) + '…' : b.input
  return `<div class="tool">
    <div class="tline"><span class="tick">⏺</span> <span class="tname">moodle · ${esc(b.name)}</span> <code class="targs">${esc(input)}</code></div>
    ${b.result ? `<div class="tresult">⎿ ${md(b.result.length > 220 ? b.result.slice(0, 220) + '…' : b.result)}</div>` : ''}
  </div>`
}).join('')

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d1117; font-family:-apple-system,'Segoe UI',sans-serif; padding:32px; }
  .frame { max-width:900px; margin:0 auto; background:#161b22; border:1px solid #30363d; border-radius:14px; overflow:hidden; }
  .bar { padding:12px 18px; border-bottom:1px solid #30363d; color:#7d8590; font-size:12px; display:flex; gap:8px; align-items:center; }
  .dots span { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; }
  .body { padding:20px 24px; }
  .user { background:#1c2431; border:1px solid #2c3a52; color:#e6edf3; border-radius:10px; padding:12px 16px; font-size:14px; margin-bottom:18px; }
  .user .label { color:#79c0ff; font-size:11px; font-weight:600; letter-spacing:.4px; margin-bottom:4px; }
  .msg { color:#c9d1d9; font-size:14px; line-height:1.55; margin:14px 2px; }
  .tool { margin:10px 0; }
  .tline { font-family:ui-monospace,'SF Mono',monospace; font-size:12.5px; color:#e6edf3; }
  .tick { color:#3fb950; }
  .tname { color:#d2a8ff; font-weight:600; }
  .targs { color:#7d8590; }
  .tresult { font-family:ui-monospace,monospace; font-size:12px; color:#8b949e; margin:4px 0 0 18px; line-height:1.5; }
  .tresult strong { color:#c9d1d9; }
</style></head><body>
  <div class="frame">
    <div class="bar"><span class="dots"><span style="background:#ff5f57"></span><span style="background:#febc2e"></span><span style="background:#28c840"></span></span>${esc(title)}</div>
    <div class="body">
      <div class="user"><div class="label">USER</div>${md(prompt ?? '')}</div>
      ${rows}
    </div>
  </div>
</body></html>`

const tmp = resolve(join(dirname(outPath), '.session.html'))
writeFileSync(tmp, html)
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new',
})
const page = await browser.newPage()
await page.setViewport({ width: 1000, height: 100, deviceScaleFactor: 2 })
await page.goto(`file://${tmp}`)
const height = await page.evaluate(() => document.body.scrollHeight)
await page.setViewport({ width: 1000, height, deviceScaleFactor: 2 })
await page.screenshot({ path: resolve(outPath) })
await browser.close()
unlinkSync(tmp)
console.log('[shot]', outPath)
