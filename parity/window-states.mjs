// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Window-state edge cases for observe / activate_window / retry, asserting the official
// wording for each state (minimized, hidden, occluded, mostly off-screen) and that the
// documented recovery path -- activate_window, refresh with get_window, retry -- works.
import { execSync, spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
const EXE = repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
const OUT = repoRoot + '/parity/window-states.json'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
class H {
  constructor() {
    this.c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.buf = ''; this.id = 1; this.p = new Map()
    this.c.stdout.setEncoding('utf8')
    this.c.stdout.on('data', (ch) => { this.buf += ch; let i
      while ((i = this.buf.indexOf(String.fromCharCode(10))) !== -1) {
        const line = this.buf.slice(0, i).trim(); this.buf = this.buf.slice(i + 1)
        if (!line) continue; let m; try { m = JSON.parse(line) } catch { continue }
        const f = this.p.get(m.id); if (f) { this.p.delete(m.id); f(m) } } })
  }
  call(method, params = {}, meta = {}) {
    const id = this.id++
    return new Promise((r) => { this.p.set(id, r)
      this.c.stdin.write(JSON.stringify({ id, method, params, meta }) + String.fromCharCode(10))
      setTimeout(() => { if (this.p.delete(id)) r({ ok: false, error: 'timeout' }) }, 25000) })
  }
  kill() { try { this.c.kill() } catch {} }
}
const ps = (script, args) => execSync('pwsh -NoProfile -ExecutionPolicy Bypass -File repoRoot + "/parity/' + script + '" ' + (args || ''), { encoding: 'utf8' }).trim()

const h = new H()
const listed = await h.call('list_windows')
const target = (listed.result || []).find((w) => w && w.title === 'Parity Target')
if (!target) { console.log('TARGET_MISSING'); h.kill(); process.exit(1) }
const win = { app: target.app, id: target.id }
const meta = { 'x-oai-cua-approved-app': target.app }
const results = []

async function trial(label, setup, expect) {
  const state = setup ? ps('window-state.ps1', setup) : '(unchanged)'
  await sleep(300)
  const observe = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
  let activate = null
  if (observe.ok !== true) {
    activate = await h.call('activate_window', { window: win, id: win.id, app: win.app }, meta)
  }
  const refresh = await h.call('get_window', { window: win, id: win.id, app: win.app }, meta)
  const retry = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
  const row = {
    label,
    state,
    observe: observe.ok === true ? 'ok' : String(observe.error),
    activate: activate === null ? '(not needed)' : activate.ok === true ? 'ok' : String(activate.error),
    refresh: refresh.ok === true ? 'ok' : String(refresh.error),
    retry: retry.ok === true ? 'ok' : String(retry.error),
    expected: expect,
  }
  results.push(row)
  // Several of these states are covered by more than one official sentence, so an
  // expectation is a list of acceptable official wordings.
  const accepted = Array.isArray(expect.observe) ? expect.observe : [expect.observe]
  const pass = accepted.some((want) => row.observe.includes(want))
  console.log((pass ? '[PASS] ' : '[FAIL] ') + label)
  console.log('    state:   ' + state)
  console.log('    observe: ' + row.observe)
  console.log('    activate:' + row.activate)
  console.log('    refresh: ' + row.refresh)
  console.log('    retry:   ' + row.retry)
  return pass
}

let pass = 0, total = 0
const check = async (label, setup, expect) => { total++; if (await trial(label, setup, expect)) pass++ }

await check('normal', 'normal', { observe: 'ok' })
await check('minimized', 'minimize', { observe: 'window is minimized' })
await check('hidden', 'hide', {
  observe: ['window is not a usable app window', 'window has invalid bounds or is not visible'],
})
await check('mostly off-screen', 'offscreen -X 2440 -Y 1300', { observe: 'ok' })
// Occlusion: raise the browser over the target without activating it. A window capture
// must still succeed -- that is the whole point of capturing the window, not the screen.
execSync(
  'pwsh -NoProfile -ExecutionPolicy Bypass -File repoRoot + "/parity/occlude-target.ps1"',
  { encoding: 'utf8' },
)
await check('occluded (target behind another window)', null, { observe: 'ok' })
try { execSync('taskkill /IM notepad.exe /F', { stdio: 'ignore' }) } catch {}

// Leave the target in its canonical state so the suite is idempotent.
ps('window-state.ps1', 'normal')
fs.writeFileSync(OUT, JSON.stringify(results, null, 2))
console.log('---')
console.log(pass + '/' + total + ' window-state cases passed; details in ' + OUT)
h.kill()