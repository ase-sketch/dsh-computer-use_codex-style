import { spawn } from 'node:child_process'
// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

const EXE = repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
let buf = ''; let id = 1; const pend = new Map()
c.stderr.setEncoding('utf8'); c.stderr.on('data', (d) => console.log('STDERR ' + String(d).slice(0, 300)))
c.stdout.setEncoding('utf8')
c.stdout.on('data', (ch) => { buf += ch; let i
  while ((i = buf.indexOf(String.fromCharCode(10))) !== -1) {
    const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1)
    if (!line) continue; let m; try { m = JSON.parse(line) } catch { continue }
    const f = pend.get(m.id); if (f) { pend.delete(m.id); f(m) } } })
const call = (method, params = {}, meta = {}) => new Promise((r) => { const i = id++; pend.set(i, r)
  c.stdin.write(JSON.stringify({ id: i, method, params, meta }) + String.fromCharCode(10))
  setTimeout(() => { if (pend.delete(i)) r({ ok: false, error: 'timeout' }) }, 30000) })
await sleep(1500)
const listed = await call('list_windows')
const t = (listed.result || []).find((w) => w.title === 'Parity Target')
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
console.log('target app = ' + t.app)
const obs = await call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
console.log('observe ok=' + obs.ok + ' err=' + (obs.error || '-'))
const shot = obs.result?.screenshots?.[0]
console.log('shot id = ' + (shot && shot.id))
const click = await call('click', { window: win, screenshotId: shot.id, x: 300, y: 200 }, meta)
console.log('CLICK resp: ' + JSON.stringify(click).slice(0, 300))
await sleep(900)
const d = await call('diagnostic_state')
const o = d.result.overlayState
console.log('overlay: ' + JSON.stringify({ visible: o.visible, motionActive: o.motionActive, cursor: [o.cursorScreenX, o.cursorScreenY], motionDurationMs: o.motionDurationMs, motionFrames: o.motionFrames }))
c.kill()