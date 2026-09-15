// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Host-plane lifecycle wiring: does a real `turn/end` actually release the overlay?
//
// This mounts the plugin the way the host composition does (host plane, untagged scope),
// creates a session the way the agent loop does (through the host context, i.e. a
// *bare* session), appends the real `turn/end` event, and observes whether the service
// releases the overlay. It also pins the reason the release cannot live in the user-agent
// preset: scope-filtered dispatch never reaches a descendant scope.
//
// Run from the harness checkout, where tsx resolves the plugin's peer dependencies:
//   node --import tsx/esm parity/plugin-lifecycle.mjs
import { Context } from '@deepseek-ai/cordis'
import { createScope, scopeOf, scopeTarget } from '@deepseek-ai/dsh-scope'
import SessionStore from '@deepseek-ai/dsh-session'
import ComputerUseService from '../src/index.js'

const gates = []
const gate = (name, ok, detail) => gates.push({ name, ok: Boolean(ok), detail: String(detail ?? '') })

const ctx = new Context()
await ctx.plugin(SessionStore)
await ctx.plugin(ComputerUseService, {})
const service = ctx.dshComputerUse
if (!service) throw new Error('the host service did not register itself as dshComputerUse')
let releases = 0
service.releaseOverlay = () => { releases += 1; return Promise.resolve({ ok: true }) }

// A preset-shaped scope, i.e. what the user-agent composition mounts its rows in.
let presetCtx
await ctx.plugin(Object.assign((inner) => { presetCtx = createScope(inner, { agentPreset: 'probe' }).ctx }, { inject: ['sessions'] }))
let presetSaw = 0
presetCtx.on('session/event', (_session, event) => { if (event?.type === 'turn/end') presetSaw += 1 })

// Exactly how the loop creates sessions: through the host context, so the session is bare.
const session = ctx.sessions.create()
gate('session is entered from the host scope', scopeOf(ctx) === undefined, 'host context carries no scope tag')
session.append('turn/start', { turn: 1 })
session.append('turn/end', { turn: 1, reason: { kind: 'completed' } })
await Promise.resolve()
gate('turn/end releases the overlay from the host-plane service', releases === 1, 'releases=' + releases)
gate('a preset-scoped listener never hears the session event', presetSaw === 0, 'presetSaw=' + presetSaw)

// Cross-session safety: the sidecar is process-wide, so another session ending its turn
// must not hide the overlay of the session that is driving the desktop.
service.lastConversationId = String(session.id)
const other = ctx.sessions.create()
other.append('turn/start', { turn: 1 })
other.append('turn/end', { turn: 1, reason: { kind: 'completed' } })
await Promise.resolve()
gate('another session\'s turn/end leaves the owning overlay alone', releases === 1, 'releases=' + releases)
session.append('turn/start', { turn: 2 })
session.append('turn/end', { turn: 2, reason: { kind: 'aborted', reason: 'user' } })
await Promise.resolve()
gate('the owning session releases again on its next turn end', releases === 2, 'releases=' + releases)

// A disposed session must also release, and only for the owning conversation.
service.lastConversationId = String(session.id)
const beforeDispose = releases
ctx.emit('session/disposed', other)
await Promise.resolve()
gate('session/disposed of a foreign session does not release', releases === beforeDispose, 'releases=' + releases)
ctx.emit('session/disposed', session)
await Promise.resolve()
gate('session/disposed of the owning session releases', releases === beforeDispose + 1, 'releases=' + releases)
gate('the released conversation is forgotten', service.lastConversationId === null, String(service.lastConversationId))

// The raw scope rule that made the preset-plane hook dead code, asserted directly.
let tagged = 0
let untagged = 0
const scope = createScope(ctx, { agentPreset: 'rule' })
scope.ctx.on('probe/event', () => { tagged += 1 })
ctx.on('probe/event', () => { untagged += 1 })
const bare = ctx.sessions.create()
ctx.emit(scopeTarget(bare, scopeOf(ctx)), 'probe/event')
gate('untagged listeners receive a subject-less dispatch', untagged === 1, 'untagged=' + untagged)
gate('tagged listeners stay excluded from a subject-less dispatch', tagged === 0, 'tagged=' + tagged)

const failed = gates.filter((g) => !g.ok)
for (const g of gates) console.log((g.ok ? 'PASS ' : 'FAIL ') + g.name + (g.ok ? '' : '  ' + g.detail))
console.log(failed.length === 0 ? 'plugin-lifecycle: ' + gates.length + '/' + gates.length + ' PASS' : 'plugin-lifecycle: ' + failed.length + ' FAILED')
process.exit(failed.length === 0 ? 0 : 1)