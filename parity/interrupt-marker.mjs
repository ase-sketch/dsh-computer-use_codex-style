// Interrupt-marker lifecycle gate (live helper).
//
// The marker `<home>/cache/computer-use/interrupts/<session>/<turn>` is per-turn state: the
// transport refuses every later call in that turn after the user presses Escape. DSH used to
// only ever WRITE it, so one Escape refused that scope forever -- with the plugin's constant
// fallback turn id (`turnId: callId || 'turn'`) an hours-old 0-byte file made the helper
// answer every request with "stopped by the user with the physical Escape key". Three Wave-3
// agents diagnosed it independently. This gate covers the two fixes:
//   1. a marker older than the scope this process first saw is IGNORED and DELETED, and
//   2. `end_turn` deletes the current scope's marker.
//
// It needs no desktop: only `list_windows` is called.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')
const EXE = path.join(ROOT, 'helper-rs/target/release/dsh-computer-use.exe')
const HOME = process.env.DSH_HOME || process.env.CODEX_HOME || path.join(os.homedir(), '.dsh')
const safe = (v) => String(v).replace(/[^A-Za-z0-9._-]/g, '_')
const markerFor = (session, turn) => path.join(HOME, 'cache', 'computer-use', 'interrupts', safe(session), safe(turn))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class Helper {
  constructor() {
    this.c = spawn(EXE, ['--parent-pid', String(process.pid)], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.buf = ''; this.id = 1; this.p = new Map()
    this.c.stdout.setEncoding('utf8')
    this.c.stdout.on('data', (ch) => { this.buf += ch; let i
      while ((i = this.buf.indexOf(String.fromCharCode(10))) !== -1) { const l = this.buf.slice(0, i).trim(); this.buf = this.buf.slice(i + 1); if (!l) continue; let m; try { m = JSON.parse(l) } catch { continue }; const f = this.p.get(m.id); if (f) { this.p.delete(m.id); f(m) } } })
  }
  call(method, params = {}, meta = {}, t = 20000) { const id = this.id++
    return new Promise((r) => { this.p.set(id, r); this.c.stdin.write(JSON.stringify({ id, method, params, meta }) + String.fromCharCode(10)); setTimeout(() => { if (this.p.delete(id)) r({ ok: false, error: 'TIMEOUT' }) }, t) }) }
  kill() { try { this.c.kill() } catch {} }
}

const results = []
const gate = (name, ok, detail) => { results.push({ name, ok, detail }); console.log((ok ? 'PASS ' : 'FAIL ') + name + '  ' + detail) }

// The scope the plugin falls back to when a call carries no turn id.
const SESSION = 'dsh', TURN = 'turn'
const marker = markerFor(SESSION, TURN)
const existedBefore = fs.existsSync(marker)

// 1. A leftover marker must not refuse today's call, and must be cleaned up.
if (!existedBefore) fs.mkdirSync(path.dirname(marker), { recursive: true })
if (!existedBefore) fs.writeFileSync(marker, '')
// Backdate it: the fix compares the marker's mtime with the moment this process first saw the
// scope, and a file written *now* would legitimately count as live.
const old = new Date(Date.now() - 3600 * 1000)
fs.utimesSync(marker, old, old)

const h = new Helper()
await sleep(1500)
const listed = await h.call('list_windows', {}, { session_id: SESSION, turn_id: TURN })
const refused = listed && listed.ok === false && /physical Escape key/.test(String(listed.error))
gate('interrupt: a stale marker does not refuse the call', listed && listed.ok === true && !refused, 'ok=' + (listed && listed.ok) + ' windows=' + (Array.isArray(listed.result) ? listed.result.length : '?') + (refused ? ' (REFUSED)' : ''))
gate('interrupt: the stale marker is deleted (self-healing)', !fs.existsSync(marker), marker)

// 2. A live marker still refuses, and `end_turn` clears it.
fs.mkdirSync(path.dirname(marker), { recursive: true })
fs.writeFileSync(marker, '')
const refusedAgain = await h.call('list_windows', {}, { session_id: SESSION, turn_id: TURN })
gate('interrupt: a live marker still refuses', refusedAgain && refusedAgain.ok === false && /physical Escape key/.test(String(refusedAgain.error)), String(refusedAgain && refusedAgain.error).slice(0, 90))
const ended = await h.call('end_turn', {}, { session_id: SESSION, turn_id: TURN })
await sleep(300)
gate('interrupt: end_turn deletes the current marker', !fs.existsSync(marker), 'end_turn ok=' + (ended && ended.ok) + ' markerExists=' + fs.existsSync(marker))
const afterEnd = await h.call('list_windows', {}, { session_id: SESSION, turn_id: TURN })
gate('interrupt: the scope serves again after end_turn', afterEnd && afterEnd.ok === true, 'ok=' + (afterEnd && afterEnd.ok))
h.kill()

const failed = results.filter((r) => !r.ok)
console.log('interrupt-marker gate: ' + (results.length - failed.length) + '/' + results.length + ' hold')
process.exit(failed.length ? 1 : 0)