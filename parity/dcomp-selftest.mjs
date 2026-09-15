// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Self-test: does DirectComposition present at all?
import { spawn, execSync } from 'node:child_process'
const EXE = repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
const c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, DSH_CU_OVERLAY_SELFTEST: '1' } })
let buf = ''; const p = new Map(); let id = 1
c.stdout.setEncoding('utf8')
c.stdout.on('data', (ch) => { buf += ch; let i
  while ((i = buf.indexOf('\n')) !== -1) { const l = buf.slice(0, i).trim(); buf = buf.slice(i + 1)
    if (!l) continue; let m; try { m = JSON.parse(l) } catch { continue }
    const f = p.get(m.id); if (f) { p.delete(m.id); f(m) } } })
const call = (method, params = {}, meta = {}) => { const i = id++; return new Promise((r) => { p.set(i, r)
  c.stdin.write(JSON.stringify({ id: i, method, params, meta }) + '\n')
  setTimeout(() => { if (p.delete(i)) r({ ok: false, error: 'timeout' }) }, 45000) }) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const list = (await call('list_windows')).result
const t = list.find((w) => w.title === 'Parity Target')
if (!t) { console.log('TARGET_MISSING'); c.kill(); process.exit(1) }
const win = { app: t.app, id: t.id }; const meta = { 'x-oai-cua-approved-app': t.app }
const o = await call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
const ck = await call('click', { window: win, screenshotId: o.result.screenshots[0].id, x: 300, y: 300 }, meta)
console.log('click -> ' + (ck.ok === true ? 'ok' : ck.error))
await sleep(1200)
const d = (await call('diagnostic_state')).result.overlayState
console.log('displayStep=' + d.displayStep + ' pillLayout=' + d.pillLayout)
try {
  console.log(execSync('pwsh -NoProfile -ExecutionPolicy Bypass -File repoRoot + "/parity/pill-probe.ps1"', { encoding: 'utf8' }).trim())
} catch (err) { console.log('capture failed: ' + String(err.message).slice(0, 200)) }
c.kill()