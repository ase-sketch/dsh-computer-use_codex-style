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
c.stdout.setEncoding('utf8')
c.stdout.on('data', (ch) => { buf += ch; let i
  while ((i = buf.indexOf(String.fromCharCode(10))) !== -1) {
    const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1)
    if (!line) continue; let m; try { m = JSON.parse(line) } catch { continue }
    const f = pend.get(m.id); if (f) { pend.delete(m.id); f(m) } } })
const call = (method, params = {}, meta = {}) => new Promise((r) => { const i = id++; pend.set(i, r)
  c.stdin.write(JSON.stringify({ id: i, method, params, meta }) + String.fromCharCode(10))
  setTimeout(() => { if (pend.delete(i)) r({ ok: false, error: 'timeout' }) }, 30000) })
const fg = async (tag) => { const d = await call('diagnostic_state'); const o = d.result.overlayState; console.log(tag + ' fg=' + d.result.foreground.exe + ' visible=' + o.visible + ' suppressed=' + o.systemCursorSuppressed) }
await sleep(1500)
const listed = await call('list_windows')
const t = (listed.result || []).find((w) => w.title === 'Parity Target')
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
await fg('start        ')
const obs = await call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
console.log('observe ok=' + obs.ok)
const shot = obs.result && obs.result.screenshots && obs.result.screenshots[0]
await fg('after observe')
const cl = await call('click', { window: win, screenshotId: shot.id, x: 300, y: 200 }, meta)
console.log('click -> ' + JSON.stringify(cl).slice(0, 200))
await fg('after click  ')
const act = await call('activate_window', { window: win, id: win.id, app: win.app }, meta)
console.log('activate_window -> ' + JSON.stringify(act).slice(0, 200))
await fg('after activate')
const cl2 = await call('click', { window: win, screenshotId: shot.id, x: 320, y: 220 }, meta)
console.log('click#2 -> ' + JSON.stringify(cl2).slice(0, 200))
c.kill()