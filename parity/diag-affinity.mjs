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
let buf = ''; let err = ''; const p = new Map(); let id = 1
c.stdout.setEncoding('utf8'); c.stderr.setEncoding('utf8')
c.stderr.on('data', (x) => { err += x })
c.stdout.on('data', (ch) => {
  buf += ch; let i
  while ((i = buf.indexOf('\n')) !== -1) {
    const l = buf.slice(0, i).trim(); buf = buf.slice(i + 1)
    if (!l) continue
    let m; try { m = JSON.parse(l) } catch { continue }
    const f = p.get(m.id); if (f) { p.delete(m.id); f(m) }
  }
})
const call = (method, params = {}, meta = {}) => new Promise((r) => { const i = id++; p.set(i, r); c.stdin.write(JSON.stringify({ id: i, method, params, meta }) + '\n'); setTimeout(() => { if (p.delete(i)) r({ ok: false, error: 'timeout' }) }, 30000) })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const list = (await call('list_windows')).result
const t = list.find((w) => w.title === 'Parity Target')
console.log('target:', t ? t.app + ' ' + t.id : 'MISSING')
if (!t) { c.kill(); console.log(err.slice(0, 500)); process.exit(1) }
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
let obs = null
for (let a = 0; a < 8 && !obs; a++) { const r = await call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta); if (r.ok === true) obs = r.result; else await sleep(1200) }
const s = obs.screenshots[0]
await call('click', { window: win, screenshotId: s.id, x: Math.round(s.width/2), y: Math.round(s.height/2) }, meta)
await call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
await sleep(3000)
console.log('--- helper stderr (diag lines) ---')
console.log(err.split('\n').filter((l) => l.includes('[diag]')).slice(-8).join('\n'))
console.log('--- holding 30s for external probe ---')
await sleep(30000)
c.kill()