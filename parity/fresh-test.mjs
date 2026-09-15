// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Content freshness probe: does a capture taken right after an action already show
// that action's effect on window content (not just the cosmetic cursor)?
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
const EXE = repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
class H {
  constructor() {
    this.c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.buf = ''; this.id = 1; this.p = new Map()
    this.c.stdout.setEncoding('utf8')
    this.c.stdout.on('data', (ch) => { this.buf += ch; let i
      while ((i = this.buf.indexOf('\n')) !== -1) { const l = this.buf.slice(0, i).trim(); this.buf = this.buf.slice(i + 1)
        if (!l) continue; let m; try { m = JSON.parse(l) } catch { continue }
        const f = this.p.get(m.id); if (f) { this.p.delete(m.id); f(m) } } })
  }
  call(method, params = {}, meta = {}) {
    const id = this.id++
    return new Promise((r) => { this.p.set(id, r)
      this.c.stdin.write(JSON.stringify({ id, method, params, meta }) + '\n')
      setTimeout(() => { if (this.p.delete(id)) r({ ok: false, error: 'timeout' }) }, 45000) })
  }
  kill() { try { this.c.kill() } catch {} }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const h = new H()
const list = (await h.call('list_windows')).result
const t = list.find((w) => w.title === 'Parity Target')
if (!t) { console.log('TARGET_MISSING'); h.kill(); process.exit(1) }
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
const shot = async (name) => {
  const o = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
  if (o.ok !== true || !o.result.screenshots.length) { console.log(name + ' failed: ' + o.error); return null }
  const s = o.result.screenshots[0]
  const out = path.join(repoRoot + '/parity', name + '.jpg')
  fs.writeFileSync(out, Buffer.from(String(s.url).split(',')[1], 'base64'))
  return s
}
const s0 = await shot('fresh-0')
// Click the Parity Button: the app answers by rewriting the text box, so the effect
// is a content change well away from the cursor sprite.
const r = await h.call('click', { window: win, screenshotId: s0.id, x: 184, y: 239 }, meta)
console.log('button click -> ' + (r.ok === true ? 'ok' : r.error))
await sleep(700)
const s1 = await shot('fresh-1')
console.log('shot sizes ' + (s0 ? s0.width + 'x' + s0.height : '-') + ' / ' + (s1 ? s1.width + 'x' + s1.height : '-'))
// Now move the pointer far from the text box and take a settled capture.
const r2 = await h.call('click', { window: win, screenshotId: s1.id, x: 800, y: 520 }, meta)
console.log('move click -> ' + (r2.ok === true ? 'ok' : r2.error))
await sleep(900)
await shot('fresh-2')
h.kill()
