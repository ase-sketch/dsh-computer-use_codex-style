// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Decisive cursor-visibility test.
// The helper now exposes overlayState {cursorScreenX/Y, windows[].excludedFromCapture},
// so this test can (a) confirm nothing excludes the cursor and (b) compute exactly
// where the glyph must appear in the capture, then verify the pixels.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
const EXE = repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
const OUT = path.join(repoRoot + '/parity', 'cursor-test.jpg')
class H {
  constructor() {
    this.c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.buf = ''; this.id = 1; this.p = new Map()
    this.c.stdout.setEncoding('utf8')
    this.c.stdout.on('data', (ch) => { this.buf += ch; let i
      while ((i = this.buf.indexOf('\n')) !== -1) { const l = this.buf.slice(0, i).trim(); this.buf = this.buf.slice(i + 1);
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
let obs = null
for (let a = 0; a < 8 && !obs; a++) {
  const r = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
  if (r.ok === true && r.result.screenshots.length) obs = r.result; else await sleep(1200)
}
if (!obs) { console.log('OBSERVE_FAILED'); h.kill(); process.exit(1) }
const s = obs.screenshots[0]
console.log('capture', s.id, s.width + 'x' + s.height, 'origin', s.originX + ',' + s.originY)
const diag0 = (await h.call('diagnostic_state')).result.overlayState
console.log('overlay before input: visible=' + diag0.visible + ' cursor=' + diag0.cursorScreenX + ',' + diag0.cursorScreenY)
for (const w of diag0.windows || []) console.log('  win', w.class, 'visible=' + w.visible, 'excluded=' + w.excludedFromCapture)
// Click a point well inside the client area, avoiding the caption bar.
const cx = Math.round(s.width * 0.35), cy = Math.round(s.height * 0.6)
const r = await h.call('click', { window: win, screenshotId: s.id, x: cx, y: cy }, meta)
console.log('click(' + cx + ',' + cy + '):', r.ok === true ? 'ok' : r.error)
await sleep(2500)
const diag1 = (await h.call('diagnostic_state')).result.overlayState
console.log('overlay after input: visible=' + diag1.visible + ' cursor=' + diag1.cursorScreenX + ',' + diag1.cursorScreenY + ' lastInput=' + diag1.lastInputScreenX + ',' + diag1.lastInputScreenY)
for (const w of diag1.windows || []) console.log('  win', w.class, 'visible=' + w.visible, 'excluded=' + w.excludedFromCapture)
// Capture again while the overlay is up, and report the mapping data the pixel
// check needs: where the cursor is on screen relative to the capture viewport.
const obs2 = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
if (obs2.ok === true && obs2.result.screenshots.length) {
  const s2 = obs2.result.screenshots[0]
  fs.writeFileSync(OUT, Buffer.from(String(s2.url).split(',')[1], 'base64'))
  const diag2 = (await h.call('diagnostic_state')).result.overlayState
  console.log('post-capture overlay: visible=' + diag2.visible + ' cursor=' + diag2.cursorScreenX + ',' + diag2.cursorScreenY)
  console.log('capture2', s2.width + 'x' + s2.height, 'origin', s2.originX + ',' + s2.originY)
  const scale = s2.width / (s2.nativeWidth || s2.width)
  const imgX = (diag2.cursorScreenX - s2.originX) * scale
  const imgY = (diag2.cursorScreenY - s2.originY) * scale
  console.log('MAPPING cursor screen ' + diag2.cursorScreenX + ',' + diag2.cursorScreenY + ' -> image ' + Math.round(imgX) + ',' + Math.round(imgY) + ' (scale ' + scale.toFixed(4) + ')')
  console.log('  in-bounds: ' + (imgX >= 0 && imgX < s2.width && imgY >= 0 && imgY < s2.height))
  const cap = (await h.call('diagnostic_state')).result.captureState
  console.log('capture path: ' + JSON.stringify(cap))
  console.log('saved ' + OUT + ' (' + fs.statSync(OUT).size + ' bytes)')
} else { console.log('second capture failed') }
h.kill()