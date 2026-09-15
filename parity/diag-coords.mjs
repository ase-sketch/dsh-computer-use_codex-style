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

const EXE = repoRoot + '\\helper-rs\\target\\release\\dsh-computer-use.exe'
const c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
let buf = ''; const p = new Map(); let id = 1
c.stdout.setEncoding('utf8')
c.stdout.on('data', (ch) => { buf += ch; let i
  while ((i = buf.indexOf('\n')) !== -1) { const l = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (!l) continue
    let m; try { m = JSON.parse(l) } catch { continue } const f = p.get(m.id); if (f) { p.delete(m.id); f(m) } } })
const call = (method, params = {}, meta = {}) => new Promise((r) => { const i = id++; p.set(i, r); c.stdin.write(JSON.stringify({ id: i, method, params, meta }) + '\n'); setTimeout(() => { if (p.delete(i)) r({ ok: false, error: 'timeout' }) }, 30000) })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const list = (await call('list_windows')).result
const t = list.find((w) => w.title === 'Parity Target')
if (!t) { console.log('TARGET_MISSING'); c.kill(); process.exit(1) }
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
let obs = null
for (let a = 0; a < 8 && !obs; a++) { const r = await call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta); if (r.ok === true) obs = r.result; else await sleep(1200) }
const s = obs.screenshots[0]
console.log('=== window geometry from the helper ===')
console.log('window.app/id        :', JSON.stringify(obs.window))
console.log('screenshot           : id=' + s.id + ' width=' + s.width + ' height=' + s.height + ' native=' + s.nativeWidth + 'x' + s.nativeHeight)
console.log('screenshot origin    :', s.originX + ',' + s.originY)
const diag = (await call('diagnostic_state')).result
console.log('diagnostic lastWindowIdentity:', JSON.stringify(diag.lastWindowIdentity))
console.log('diagnostic bounds            :', JSON.stringify(diag.bounds))
console.log('diagnostic lease.viewport    :', JSON.stringify(diag.lease && diag.lease.window), JSON.stringify(diag.lease && diag.lease.screenshotId))
const spaces = obs.spaces || []
console.log('spaces               :', JSON.stringify(spaces.map((x) => ({ id: x.id, space: x.space, o: [x.originX, x.originY], w: x.width, h: x.height, nw: x.nativeWidth, nh: x.nativeHeight }))))
console.log('=== consistency checks ===')
console.log('expected physical window origin from list_windows: unknown here')
console.log('image w/native w ratio =', (s.width / s.nativeWidth).toFixed(4))
console.log('if the click x,y are window-relative LOGICAL px, then screenX = originX + x*scale')
for (const [x, y] of [[336, 378], [0, 0], [s.width, s.height]]) {
  console.log('  (' + x + ',' + y + ') -> screen ' + (s.originX + x) + ',' + (s.originY + y) + '  (scale 1.0)')
}
c.kill()