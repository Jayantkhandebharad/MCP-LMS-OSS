/**
 * Render the REAL sampling round-trip (captured by scripts/demo/sampling_demo.py)
 * as a blog image: server-initiated request (with fenced untrusted content) ->
 * client's model returns questions -> tool result.
 *
 *   node phase6_sampling_shot.mjs
 */
import puppeteer from 'puppeteer-core'
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(join(here, '../../docs/screenshots'))
const d = JSON.parse(readFileSync('/tmp/sampling-demo.json', 'utf8'))
const esc = (s) => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

const fenceHighlighted = esc(d.user_message)
  .replace(/(&lt;UNTRUSTED_COURSE_CONTENT&gt;)/g, '<span class="fence">$1</span>')
  .replace(/(&lt;\/UNTRUSTED_COURSE_CONTENT&gt;)/g, '<span class="fence">$1</span>')

const answer = esc(d.tool_result).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d1117; font-family:-apple-system,'Segoe UI',sans-serif; padding:34px; color:#c9d1d9; }
  .wrap { max-width:1080px; margin:0 auto; }
  h1 { color:#e6edf3; font-size:19px; margin-bottom:4px; }
  .sub { color:#7d8590; font-size:13px; margin-bottom:22px; }
  .step { margin-bottom:18px; }
  .label { font-size:12px; font-weight:600; margin-bottom:6px; letter-spacing:.3px; }
  .s1 { color:#d2a8ff; } .s2 { color:#3fb950; } .s3 { color:#79c0ff; }
  .box { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:14px 16px;
         font-family:ui-monospace,'SF Mono',monospace; font-size:12px; line-height:1.6; white-space:pre-wrap; }
  .box.sys { border-left:3px solid #d2a8ff; }
  .box.req { border-left:3px solid #d2a8ff; max-height:280px; overflow:hidden; }
  .box.res { border-left:3px solid #3fb950; }
  .fence { color:#f0883e; font-weight:600; }
  .cap { color:#7d8590; font-size:11px; margin-top:5px; }
  .arrow { color:#484f58; text-align:center; font-size:18px; margin:2px 0; }
</style></head><body>
  <div class="wrap">
    <h1>MCP sampling: the server borrows the client's model</h1>
    <div class="sub">A real round-trip captured from the running server. The tool <code>generate_practice_quiz</code> asks the CLIENT to run a completion — the server holds no LLM key.</div>

    <div class="step">
      <div class="label s1">① Server → Client &nbsp; sampling/createMessage &nbsp; system prompt</div>
      <div class="box sys">${esc(d.system_prompt)}</div>
      <div class="cap">The system turn tells the model to treat tagged content as DATA, never instructions.</div>
    </div>

    <div class="step">
      <div class="label s1">② Server → Client &nbsp; the user turn (real Moodle course text, fenced as untrusted)</div>
      <div class="box req">${fenceHighlighted}</div>
      <div class="cap">Untrusted teacher-authored content sits inside <span class="fence">&lt;UNTRUSTED_COURSE_CONTENT&gt;</span> — the prompt-injection guardrail (safety.py). Truncated for display.</div>
    </div>

    <div class="arrow">↓ the client runs its model, and may approve / edit / reject the request ↓</div>

    <div class="step">
      <div class="label s2">③ Client's model → Server → the tool result</div>
      <div class="box res">${answer}</div>
      <div class="cap">Generated questions grounded in the real material, returned to the agent. (Claude Code doesn't support sampling — this run used a sampling-capable demo client.)</div>
    </div>
  </div>
</body></html>`

const tmp = resolve(join(outDir, '.p6.html'))
writeFileSync(tmp, html)
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new',
})
const page = await browser.newPage()
await page.setViewport({ width: 1160, height: 100, deviceScaleFactor: 2 })
await page.goto(`file://${tmp}`)
const h = await page.evaluate(() => document.body.scrollHeight)
await page.setViewport({ width: 1160, height: h, deviceScaleFactor: 2 })
await page.screenshot({ path: join(outDir, 'phase6-sampling-demo.png') })
await browser.close()
unlinkSync(tmp)
console.log('[shot] phase6-sampling-demo.png')
