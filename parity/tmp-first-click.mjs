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
const fg = async (tag) => { const d = await call('diagnostic_state'); console.log(tag + ' fg=' + d.result.foreground.exe + '(' + d.result.foreground.inputHwnd + ')') }
await sleep(1500)
const listed = await call('list_windows')
const t = (listed.result || []).find((w) => w.title === 'Parity Target')
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
await fg('start')
const obs = await call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
if (obs.ok !== true) { console.log('OBSERVE FAILED: ' + JSON.stringify(obs).slice(0, 300)); c.kill(); process.exit(1) }
const shot = obs.result.screenshots[0]
await fg('after observe')
for (const n of [1, 2, 3]) {
  const r = await call('click', { window: win, screenshotId: shot.id, x: 300, y: 200 }, meta)
  console.log('click#' + n + ' -> ' + JSON.stringify(r).slice(0, 160))
  await sleep(800)
  await fg('  after click#' + n)
}
c.kill()