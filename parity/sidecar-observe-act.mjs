// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Sidecar-level observe -> act gate.
//
// V3 said it plainly: every other gate in this repo drives the helper DIRECTLY, so the
// plugin's own turn bookkeeping was invisible to all of them. This gate goes through the real
// `Sidecar` and the real turn-meta builder, and it is the gate that would have caught the
// regression that broke the first real end-to-end task (2026-09-14):
//
//   tool.js stamped `turnId = exec.callId`  (a NEW id per tool call)
//   sidecar.js#ensureTurn sends `end_turn` whenever the turn key changes
//   the helper treats `end_turn` as 'flush the observation lease'
//   => every input action ran with no captured window and answered
//      'call get_window_state before using this window' /
//      'coordinate input target is unavailable'.
//
// Case order is deliberate: the contract case runs first, because the control case leaves the
// helper with no observation lease by construction.
//
// Run from the harness checkout (tsx resolves the plugin's peer deps):
//   from the harness checkout: node --import tsx/esm parity/sidecar-observe-act.mjs
import { spawn, execFileSync } from 'node:child_process'
import { Context } from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import ComputerUseService from '../src/index.js'
import { turnMetaFor } from '../src/tool.js'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const gates = []
const gate = (name, ok, detail) => { gates.push({ name, ok: Boolean(ok) }); console.log((ok ? 'PASS ' : 'FAIL ') + name + '  ' + (detail ?? '')) }
const identityError = (error) => /coordinate input target is unavailable|call get_window_state before using this window/.test(String(error || ''))

// A run must not inherit another run's helper (the overlay and the observation lease are
// process-scoped).
try { execFileSync('pwsh', ['-NoProfile', '-Command', 'Get-Process dsh-computer-use -ErrorAction SilentlyContinue | Stop-Process -Force'], { stdio: 'ignore' }) } catch {}
await sleep(400)

let running = 'no'
try {
  running = execFileSync('pwsh', ['-NoProfile', '-Command', "if (Get-Process ParityTarget -ErrorAction SilentlyContinue) { 'yes' } else { 'no' }"], { encoding: 'utf8' }).trim()
} catch {}
if (running !== 'yes') {
  const proc = spawn(repoRoot + '/parity/ParityTarget.exe', [], { stdio: 'ignore', detached: true })
  proc.unref()
  await sleep(2500)
}
try { execFileSync('pwsh', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', repoRoot + '/parity/raise-target.ps1'], { stdio: 'ignore' }) } catch {}
await sleep(600)

const ctx = new Context()
await ctx.plugin(SessionStore)
await ctx.plugin(ComputerUseService, {})
const service = ctx.dshComputerUse
if (!service) throw new Error('the host service did not register itself as dshComputerUse')

let approvedApp = ''
const metaFor = (turnId, callId) => ({ conversationId: 'observe-act-probe', turnId, callId, ...(approvedApp ? { 'x-oai-cua-approved-app': approvedApp } : {}) })
// The sidecar rejects on helper errors; a probe needs the error object, not a throw.
async function safeCall(name, args, meta) {
  try {
    return await service.call(name, args, undefined, meta)
  } catch (error) {
    return { ok: false, error: String(error?.message || error) }
  }
}

const listed = await safeCall('list_windows', {}, metaFor('probe', 'probe-list'))
const rows = Array.isArray(listed?.value) ? listed.value : (Array.isArray(listed?.result) ? listed.result : [])
const window = rows.find((w) => String(w.title || '').includes('Parity Target'))
if (!window) { console.log('FAIL no Parity Target window'); process.exit(1) }
const spec = { app: window.app, id: window.id }
approvedApp = window.app

// ---------------------------------------------------------------------------------------
// Case 1 (contract): two calls of ONE turn keep one turn id, so observe -> act works.
const turnMetaForFn = typeof turnMetaFor === 'function' ? turnMetaFor : null
gate('tool.js exports turnMetaFor(service, exec)', Boolean(turnMetaForFn), typeof turnMetaFor)
const execA = { agent: { id: 'observe-act-probe' }, callId: 'call-a', rootCallId: 'call-a' }
const execB = { agent: { id: 'observe-act-probe' }, callId: 'call-b', rootCallId: 'call-a' }
// `turnMetaFor` is the plugin's meta; the approved-app header travels separately (the plugin
// answers an approval request with it), so the probe merges it in for gated calls.
const withApproval = (meta) => ({ ...meta, ...(approvedApp ? { 'x-oai-cua-approved-app': approvedApp } : {}) })
const metaA = withApproval(turnMetaForFn ? turnMetaForFn(service, execA) : metaFor('turn', 'call-a'))
const metaB = withApproval(turnMetaForFn ? turnMetaForFn(service, execB) : metaFor('turn', 'call-b'))
gate('tool.js: two calls of one turn share the turn id', metaA.turnId === metaB.turnId, 'turnId A=' + metaA.turnId + ' B=' + metaB.turnId)
gate('tool.js: the call id is still forwarded for approvals', metaB.callId === 'call-b', 'callId=' + metaB.callId)
gate('tool.js: the turn id is not the per-call id', String(metaB.turnId) !== 'call-b', 'turnId=' + metaB.turnId)

const obs = await safeCall('get_window_state', { window: spec, include_screenshot: true, include_text: true }, metaA)
const shot = obs?.value?.screenshots?.[0]?.id
const size = obs?.value?.screenshots?.[0]
gate('sidecar: observe succeeds with the plugin meta', Boolean(shot), 'screenshotId=' + shot)

const click = await safeCall('click', { window: spec, screenshotId: shot, x: Math.round((size?.width ?? 800) / 2), y: Math.round((size?.height ?? 600) / 3) }, metaB)
gate('sidecar: click right after get_window_state succeeds (the real task failure)', click?.ok === true, 'ok=' + click?.ok + ' error=' + JSON.stringify(click?.error || ''))
const press = await safeCall('press_key', { window: spec, key: 'Control_L+' }, metaB)
gate('sidecar: press_key right after get_window_state succeeds', press?.ok === true, 'ok=' + press?.ok + ' error=' + JSON.stringify(press?.error || ''))

// ---------------------------------------------------------------------------------------
// Case 2 (control): a changed turn id must still flush the lease. This is the official
// `end_turn` semantics and the mechanism behind the broken task -- it runs last on purpose.
const refreshed = await safeCall('get_window_state', { window: spec, include_screenshot: true, include_text: true }, metaB)
const shot2 = refreshed?.value?.screenshots?.[0]?.id
const perCall = await safeCall('click', { window: spec, screenshotId: shot2, x: 200, y: 60 }, metaFor('turn-2', 'call-z'))
gate(
  'sidecar: a changed turn id flushes the observation lease (official end_turn)',
  perCall?.ok === false && identityError(perCall?.error),
  'error=' + JSON.stringify(perCall?.error || ''),
)

await service.endTurn({}).catch(() => {})
try { await service.sidecar?.dispose?.() } catch {}
const failed = gates.filter((g) => !g.ok)
console.log('sidecar observe->act gate: ' + (gates.length - failed.length) + '/' + gates.length + ' hold')
process.exit(failed.length ? 1 : 0)