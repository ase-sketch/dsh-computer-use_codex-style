// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Overlay and system-pointer lifecycle: one gate per operator-visible contract.
//
// Contracts:
//   1. idle desktop: no synthetic cursor, the real pointer visible (exactly one)
//   2. overlay shown: synthetic cursor visible AND the real pointer suppressed
//      (fake cursor + visible real pointer = the reported two-cursors state)
//   3. after cancel/end_turn: overlay hidden, real pointer restored
//   4. a second show() in the same helper process still suppresses (a manual-reset
//      shutdown event left signalled used to kill every later cursor manager)
//   5. suppression survives another process restoring the system cursors
import { execSync, spawn } from 'node:child_process'
import fs from 'node:fs'
const EXE = process.env.DSH_CU_HELPER || repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
const TARGET = repoRoot + '/parity/ParityTarget.exe'
const PROBE = repoRoot + '/parity/overlay-probe.ps1'
const SUP = repoRoot + '/parity/cursor-suppression.ps1'
const RESTORE = repoRoot + '/parity/restore-cursors.ps1'
const OUT = repoRoot + '/parity/overlay-lifecycle.json'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const psfile = (f, args) => execSync('pwsh -NoProfile -ExecutionPolicy Bypass -File "' + f + '" ' + (args || ''), { encoding: 'utf8' })
const targetProc = spawn(TARGET, [], { stdio: 'ignore' })
await sleep(2000)
class H {
  constructor() {
    this.c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.buf = ''; this.id = 1; this.p = new Map(); this.err = ''
    this.c.stderr.setEncoding('utf8')
    this.c.stderr.on('data', (d) => { this.err += String(d) })
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
const h = new H()
await sleep(1500)
const state = () => {
  const raw = psfile(PROBE, '-TargetPid ' + h.c.pid)
  const p = JSON.parse(raw.split(/\r?\n/).filter((l) => l.trim().startsWith('{')).pop())
  const sup = JSON.parse(psfile(SUP).trim())
  const fake = p.overlay.filter((w) => w.class.indexOf('Pointer') >= 0 && w.visible).length > 0
  const banner = p.overlay.filter((w) => w.class.indexOf('Pointer') < 0 && w.visible).length > 0
  return { fake, banner, suppressed: sup.suppressed, managers: p.children.length, pointers: (fake ? 1 : 0) + (sup.suppressed ? 0 : 1) }
}
const diag = async () => (await h.call('diagnostic_state')).result?.overlayState ?? {}
const gates = []
const gate = (name, ok, detail) => gates.push({ name, ok: Boolean(ok), detail })
const idle = state()
gate('idle desktop shows exactly one pointer', idle.pointers === 1 && !idle.fake && !idle.suppressed, JSON.stringify(idle))
const listed = await h.call('list_windows')
const target = (listed.result || []).find((w) => w && w.title === 'Parity Target')
if (!target) { console.log('TARGET_MISSING'); h.kill(); targetProc.kill(); process.exit(1) }
const win = { app: target.app, id: target.id }
const meta = { 'x-oai-cua-approved-app': target.app }
await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
await h.call('click', { window: win, x: 120, y: 90 }, meta)
await sleep(500)
const shown = state()
gate('show draws the fake cursor', shown.fake && shown.banner, JSON.stringify(shown))
gate('show suppresses the real pointer', shown.suppressed, JSON.stringify(shown))
gate('show leaves exactly one pointer on screen', shown.pointers === 1, JSON.stringify(shown))
gate('show keeps a cursor-manager child alive', shown.managers > 0, JSON.stringify(shown))
await h.call('cancel', {})
await sleep(600)
const cancelled = state()
gate('cancel hides the overlay', !cancelled.fake && !cancelled.banner, JSON.stringify(cancelled))
gate('cancel restores the real pointer', !cancelled.suppressed, JSON.stringify(cancelled))
await h.call('click', { window: win, x: 150, y: 110 }, meta)
await sleep(500)
const again = state()
gate('a later show still suppresses the real pointer', again.suppressed && again.pointers === 1, JSON.stringify(again))
gate('a later show restarts the cursor manager', again.managers > 0, JSON.stringify(again))
const before = await diag()
const restored = JSON.parse(psfile(RESTORE).trim().split(/\r?\n/).pop())
// Harness sanity, not a product contract: it proves the disturbance really happened.
// The transient visibility cannot be asserted deterministically -- the helper re-asserts
// suppression on its own 4 s timer, so a sample may already contain a fresh suppression
// (observed once in verify-all). The contract that matters is the self-heal gate below.
gate('an external restore is applied', restored.restored, JSON.stringify(restored))
await sleep(6000)
const healed = state()
const after = await diag()
gate('suppression is re-asserted while the overlay stays up', healed.suppressed && healed.pointers === 1, JSON.stringify(healed))
gate('the re-assertion came from the re-suppression timer', (after.systemCursorReasserts ?? 0) > (before.systemCursorReasserts ?? 0), JSON.stringify({ before: before.systemCursorReasserts, after: after.systemCursorReasserts }))
gate('every suppress request was acknowledged', (after.systemCursorFailures ?? 0) === 0, JSON.stringify({ requests: after.systemCursorRequests, failures: after.systemCursorFailures }))
await h.call('end_turn', { session_id: 'gate', turn_id: 'gate' })
await sleep(700)
const ended = state()
gate('end_turn hides the overlay', !ended.fake && !ended.banner, JSON.stringify(ended))
gate('end_turn restores the real pointer', !ended.suppressed, JSON.stringify(ended))
const final = await diag()
gate('diagnostics report the suppression state', final.systemCursorSuppressed === false && final.cursorManagerAlive === false, JSON.stringify({ suppressed: final.systemCursorSuppressed, manager: final.cursorManagerAlive }))
h.kill(); targetProc.kill()
const failed = gates.filter((g) => !g.ok)
fs.writeFileSync(OUT, JSON.stringify({ gates, helperStderr: h.err.slice(0, 2000) }, null, 2))
for (const g of gates) console.log((g.ok ? 'PASS ' : 'FAIL ') + g.name + (g.ok ? '' : '  ' + g.detail))
console.log(failed.length === 0 ? 'overlay-lifecycle: ' + gates.length + '/' + gates.length + ' PASS' : 'overlay-lifecycle: ' + failed.length + ' FAILED')
process.exit(failed.length === 0 ? 0 : 1)