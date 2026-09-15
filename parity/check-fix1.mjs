// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// FIX-1: does the fake cursor appear in the captured screenshot?
// Deterministic: focus the parity target, observe (capture), refresh, click it
// (moves the overlay cursor under the mouse), then wait and capture again.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
const EXE = repoRoot + '\\helper-rs\\target\\release\\dsh-computer-use.exe'
class H {
  constructor() {
    this.c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.buf = ''; this.id = 1; this.p = new Map()
    this.c.stdout.setEncoding('utf8')
    this.c.stdout.on('data', (ch) => {
      this.buf += ch; let i
      while ((i = this.buf.indexOf('\n')) !== -1) {
        const l = this.buf.slice(0, i).trim(); this.buf = this.buf.slice(i + 1)
        if (!l) continue
        let m; try { m = JSON.parse(l) } catch { continue }
        const f = this.p.get(m.id); if (f) { this.p.delete(m.id); f(m) }
      }
    })
  }
  call(method, params = {}, meta = {}) {
    const id = this.id++
    return new Promise((r) => {
      this.p.set(id, r)
      this.c.stdin.write(JSON.stringify({ id, method, params, meta }) + '\n')
      setTimeout(() => { if (this.p.delete(id)) r({ ok: false, error: 'timeout' }) }, 45000)
    })
  }
  kill() { try { this.c.kill() } catch {} }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const h = new H()
const list = (await h.call('list_windows')).result
const t = list.find((w) => w.title === 'Parity Target')
if (!t) { console.log('target missing'); h.kill(); process.exit(1) }
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
console.log('target', t.app, t.id)

async function observe(extra = {}) {
  for (let a = 0; a < 8; a++) {
    const r = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false, ...extra }, meta)
    if (r.ok === true && r.result.screenshots && r.result.screenshots.length) return r.result
    console.log('  observe attempt', a + 1, '->', r.ok ? 'no shots' : r.error)
    await sleep(1500)
  }
  return null
}
const first = await observe()
if (!first) { console.log('first observe failed'); h.kill(); process.exit(1) }
const s1 = first.screenshots[0]
console.log('capture1', s1.width + 'x' + s1.height, 'origin', s1.originX + ',' + s1.originY)
fs.writeFileSync(repoRoot + '\\parity\\fix1-before.jpg', Buffer.from(String(s1.url).split(',')[1], 'base64'))

// Click the target's own centre so the overlay cursor lands inside this window.
const cx = Math.round(s1.width / 2), cy = Math.round(s1.height / 2)
const clicked = await h.call('click', { window: win, screenshotId: s1.id, x: cx, y: cy }, meta)
console.log('click at', cx + ',' + cy, '->', clicked.ok === true ? 'ok' : clicked.error)
console.log('overlay cursor should now be drawn at screen', (s1.originX + cx) + ',' + (s1.originY + cy))
await sleep(2500)

const second = await observe()
if (!second) { console.log('second observe failed'); h.kill(); process.exit(1) }
const s2 = second.screenshots[0]
console.log('capture2', s2.width + 'x' + s2.height, 'origin', s2.originX + ',' + s2.originY)
fs.writeFileSync(repoRoot + '\\parity\\fix1-after.jpg', Buffer.from(String(s2.url).split(',')[1], 'base64'))
console.log('saved fix1-before.jpg and fix1-after.jpg')

// Keep the helper (and therefore the overlay) alive so an external probe can
// inspect the cursor window while it is on screen.
console.log('HELPER_ALIVE pid=' + h.c.pid)
console.log('holding overlay for 45s; run the probe now')
await sleep(45000)
h.kill()
console.log('done')