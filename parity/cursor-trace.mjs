// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Trace the real system cursor and the fake overlay cursor across one click.
import { spawn, execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
const EXE = repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
const OUT = path.join(repoRoot + '/parity', 'cursor-trace.jpg')
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
const realCursor = () => {
  try {
    const out = execSync('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $p=[System.Windows.Forms.Cursor]::Position; \"$($p.X),$($p.Y)\""', { encoding: 'utf8' })
    return out.trim()
  } catch (e) { return 'ERR ' + e.message }
}
const h = new H()
const step = async (tag) => {
  const d = (await h.call('diagnostic_state')).result
  const o = d.overlayState || {}
  console.log(tag.padEnd(26) + ' real=' + realCursor().padEnd(12) + ' fake=' + o.cursorScreenX + ',' + o.cursorScreenY + ' lastInput=' + o.lastInputScreenX + ',' + o.lastInputScreenY + ' visible=' + o.visible + ' stage=' + o.cursorStage)
}
const list = (await h.call('list_windows')).result
const t = list.find((w) => w.title === 'Parity Target')
if (!t) { console.log('TARGET_MISSING'); h.kill(); process.exit(1) }
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
await step('startup')
let obs = null
for (let a = 0; a < 8 && !obs; a++) {
  const r = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
  if (r.ok === true && r.result.screenshots.length) obs = r.result; else { console.log('  observe retry: ' + r.error); await sleep(1200) }
}
if (!obs) { console.log('OBSERVE_FAILED'); h.kill(); process.exit(1) }
const s = obs.screenshots[0]
console.log('capture ' + s.id + ' ' + s.width + 'x' + s.height + ' origin ' + s.originX + ',' + s.originY)
await step('after observe')
const cx = Math.round(s.width * 0.8), cy = Math.round(s.height * 0.25)
const r = await h.call('click', { window: win, screenshotId: s.id, x: cx, y: cy }, meta)
console.log('click(' + cx + ',' + cy + ') -> ' + (r.ok === true ? 'ok' : r.error))
for (let i = 0; i < 20; i++) {
  const o = (await h.call('diagnostic_state')).result.overlayState
  console.log('  +' + String(i * 150).padStart(4) + 'ms fake=' + String(o.cursorScreenX + ',' + o.cursorScreenY).padEnd(12) + ' tick=' + o.motionTick + '/' + o.motionFrames + ' pump=' + o.pumpIters + '/' + o.pumpMsgs + '/' + o.pumpAnim + ' recr=' + o.recreates + ' drain=' + o.drainLastMs + '/' + o.drainMaxMs + ' branch=' + o.branchLastMs + '/' + o.branchMaxMs)
  if (i === 6) {
    try {
      const out = execSync('pwsh -NoProfile -ExecutionPolicy Bypass -File repoRoot + "/parity/screen-shot.ps1" repoRoot + "/parity/full-screen.png"', { encoding: 'utf8' })
      console.log('  screen capture: ' + out.trim().replace(/\r?\n/g, ' | '))
    } catch (e) { console.log('  screen capture failed: ' + String(e.message).slice(0, 200)) }
  }
  await sleep(150)
}
const obs2 = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
if (obs2.ok === true && obs2.result.screenshots.length) {
  const s2 = obs2.result.screenshots[0]
  fs.writeFileSync(OUT, Buffer.from(String(s2.url).split(',')[1], 'base64'))
  const diag2 = (await h.call('diagnostic_state')).result
  const o = diag2.overlayState
  console.log('after capture            fake=' + o.cursorScreenX + ',' + o.cursorScreenY + ' lastInput=' + o.lastInputScreenX + ',' + o.lastInputScreenY + ' visible=' + o.visible)
  console.log('capture path: ' + JSON.stringify(diag2.captureState))
  console.log('messages: ' + JSON.stringify(o.messages))
  console.log('commands: ' + JSON.stringify(o.commands) + ' total=' + o.cmdTotal + ' cmdMs=' + o.cmdLastMs + '/' + o.cmdMaxMs)
  console.log('foregrounds: total=' + o.foregroundTotal + ' ' + JSON.stringify(o.foregrounds))
  for (const w of o.windows || []) console.log('  win ' + w.class + ' visible=' + w.visible + ' excluded=' + w.excludedFromCapture + ' affinity=' + w.displayAffinity)
  console.log('image = ' + s2.width + 'x' + s2.height + ' origin ' + s2.originX + ',' + s2.originY)
  console.log('fake cursor in image: ' + (o.cursorScreenX - s2.originX) + ',' + (o.cursorScreenY - s2.originY))
  console.log('saved ' + OUT + ' (' + fs.statSync(OUT).size + ' bytes)')
  // Freshness probe: move the cosmetic cursor somewhere else and capture again.
  // If the two frames are byte-identical the WGC frame is stale, which would also
  // explain a missing cursor overlay.
  const r3 = await h.call('click', { window: win, screenshotId: s2.id, x: Math.round(s2.width * 0.2), y: Math.round(s2.height * 0.8) }, meta)
  console.log('second click -> ' + (r3.ok === true ? 'ok' : r3.error))
  for (const wait of [80, 400, 1400]) {
    await sleep(wait)
    const oo = (await h.call('diagnostic_state')).result.overlayState
    const rects = (oo.windows || []).map((w) => w.class.replace('DshComputerUseCursorOverlay', '') + '=' + JSON.stringify(w.rect)).join(' ')
    console.log('  after second click +' + wait + 'ms cursor=' + oo.cursorScreenX + ',' + oo.cursorScreenY + ' tick=' + oo.motionTick + '/' + oo.motionFrames + ' active=' + oo.motionActive + ' rects ' + rects)
  }
  // Two captures back to back with no action in between: if the second one shows
  // the moved cursor and the first does not, the capture consumes a queued frame
  // instead of the newest one.
  for (const tag of ['a', 'b', 'c']) {
    const o = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
    if (o.ok !== true || !o.result.screenshots.length) { console.log('capture ' + tag + ' failed'); continue }
    const sc = o.result.screenshots[0]
    const OUTX = path.join(repoRoot + '/parity', 'lag-' + tag + '.jpg')
    fs.writeFileSync(OUTX, Buffer.from(String(sc.url).split(',')[1], 'base64'))
    const od = (await h.call('diagnostic_state')).result.overlayState
    console.log('capture ' + tag + ': cursor image pos ' + (od.cursorScreenX - sc.originX) + ',' + (od.cursorScreenY - sc.originY) + ' bytes=' + fs.statSync(OUTX).size)
  }
} else { console.log('second capture failed: ' + obs2.error) }
await step('end')
h.kill()
