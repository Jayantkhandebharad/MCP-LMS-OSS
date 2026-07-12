/**
 * Reproducible blog screenshots of the seeded Moodle.
 *
 *   node take_screenshots.mjs --out <dir>
 *
 * Reads admin credentials from ../../docker/.env. Drives the system Chrome
 * headlessly (puppeteer-core), logs in as student1 / teacher1 / admin and
 * captures the Blog #1 shot-list. Rerun any time the seed changes.
 */
import puppeteer from 'puppeteer-core'
import { readFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const outIdx = process.argv.indexOf('--out')
const outDir = resolve(outIdx > -1 ? process.argv[outIdx + 1] : join(here, 'out'))
mkdirSync(outDir, { recursive: true })

const env = Object.fromEntries(
  readFileSync(join(here, '../../docker/.env'), 'utf8')
    .split('\n')
    .filter((l) => l.includes('=') && !l.startsWith('#'))
    .map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]),
)

const BASE = `http://localhost:${env.MOODLE_PORT ?? 8080}`
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--window-size=1400,900'],
})

async function session(username, password, shots) {
  const context = await browser.createBrowserContext()
  const page = await context.newPage()
  await page.setViewport({ width: 1400, height: 900, deviceScaleFactor: 2 })

  await page.goto(`${BASE}/login/index.php`, { waitUntil: 'networkidle2' })
  await page.type('#username', username)
  await page.type('#password', password)
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2' }),
    page.click('#loginbtn'),
  ])
  console.log(`[ok] logged in as ${username}`)

  for (const shot of shots) {
    await shot(page)
  }
  await context.close()
}

async function capture(page, name) {
  await new Promise((r) => setTimeout(r, 600)) // settle fonts/lazy bits
  await page.screenshot({ path: join(outDir, name) })
  console.log(`[shot] ${name}`)
}

/** Navigate to the href of the first link whose text contains `text`. */
async function followLink(page, text) {
  const href = await page.evaluate((t) => {
    const a = [...document.querySelectorAll('a')].find((el) => el.textContent.includes(t))
    return a ? a.href : null
  }, text)
  if (!href) throw new Error(`link not found: ${text}`)
  await page.goto(href, { waitUntil: 'networkidle2' })
}

// ---- student1: dashboard, course, page content, quiz summary + review ----
await session('student1', 'Student1!pass', [
  async (p) => {
    await p.goto(`${BASE}/my/`, { waitUntil: 'networkidle2' })
    await capture(p, 'phase1-dashboard.png')
  },
  async (p) => {
    await p.goto(`${BASE}/course/view.php?id=2`, { waitUntil: 'networkidle2' })
    await capture(p, 'phase1-course.png')
  },
  async (p) => {
    await followLink(p, 'Tools, Resources, and Prompts')
    await capture(p, 'phase1-page.png')
  },
  async (p) => {
    await p.goto(`${BASE}/course/view.php?id=2`, { waitUntil: 'networkidle2' })
    await followLink(p, 'MCP Basics Quiz')
    await capture(p, 'phase1-quiz-summary.png')
  },
  async (p) => {
    await followLink(p, 'Review')
    await capture(p, 'phase1-quiz-review.png')
  },
])

// ---- teacher1: grader report ----
await session('teacher1', 'Teacher1!pass', [
  async (p) => {
    await p.goto(`${BASE}/grade/report/grader/index.php?id=2`, { waitUntil: 'networkidle2' })
    await capture(p, 'phase1-grader-report.png')
  },
])

// ---- admin: external service function list ----
await session(env.MOODLE_ADMIN_USER ?? 'admin', env.MOODLE_ADMIN_PASS, [
  async (p) => {
    await p.goto(`${BASE}/admin/webservice/service_functions.php?id=2`, {
      waitUntil: 'networkidle2',
    })
    await capture(p, 'phase1-ws-functions.png')
  },
])

await browser.close()
console.log(`done → ${outDir}`)
