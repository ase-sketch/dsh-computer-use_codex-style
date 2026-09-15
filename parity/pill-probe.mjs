// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Keep the overlay visible long enough to photograph the status pill.
// The banner is capture-excluded on purpose, so the probe temporarily clears that
// affinity, captures the desktop, then restores it.
import { spawn, execSync } from 'node:child_process'
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
const h = new H()
const list = (await h.call('list_windows')).result
const t = list.find((w) => w.title === 'Parity Target')
if (!t) { console.log('TARGET_MISSING'); h.kill(); process.exit(1) }
const win = { app: t.app, id: t.id }
const meta = { 'x-oai-cua-approved-app': t.app }
const r = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
if (r.ok !== true) { console.log('OBSERVE_FAILED ' + r.error); h.kill(); process.exit(1) }
// The overlay is shown by an input action, not by an observation.
const s = r.result.screenshots[0]
const c = await h.call('click', { window: win, screenshotId: s.id, x: 300, y: 300 }, meta)
console.log('click -> ' + (c.ok === true ? 'ok' : c.error))
await new Promise((res) => setTimeout(res, 900))
const d = (await h.call('diagnostic_state')).result.overlayState
console.log('overlay visible=' + d.visible + ' displayComposition=' + d.displayComposition + ' cursorStage=' + d.cursorStage + ' cursor=' + d.cursorScreenX + ',' + d.cursorScreenY)
console.log('displayStep=' + d.displayStep + ' pillLayout=' + d.pillLayout + ' pill=' + JSON.stringify(d.pill))
console.log('pillSprite=' + d.pillSprite)
for (const w of d.windows || []) console.log('  win ' + w.class + ' rect=' + JSON.stringify(w.rect) + ' visible=' + w.visible)
try {
  const out = execSync('pwsh -NoProfile -ExecutionPolicy Bypass -File repoRoot + "/parity/pill-probe.ps1"', { encoding: 'utf8' })
  console.log(out.trim())
} catch (e) { console.log('probe failed: ' + String(e.message).slice(0, 300)) }
h.kill()
