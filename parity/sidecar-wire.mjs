// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// C3: the wire envelope must be the official one -- `{id,method,params,meta}` up,
// `{id,ok,result}` down. The sidecar used to write `jsonrpc: "2.0"`, which made the
// helper answer in JSON-RPC v2 shape instead (register RPC-1), and no gate looked at the
// bytes because every existing gate drives the helper directly.
import { Sidecar } from '../src/sidecar.js'

const config = {
  engineRoot: repoRoot + '',
  backend: 'windows',
  surface: 'computer',
  timeoutMs: 10000,
  launchAppTimeoutMs: 15000,
  maxImageEdge: 0,
  allowedApps: [],
}
const sidecar = new Sidecar(config)
let sent = []
let seen = []
try {
  await sidecar.request('health')
  const session = sidecar.primary
  const original = session.write.bind(session)
  session.write = (message) => { sent.push(message); return original(message) }
  await sidecar.request('tools', { surface: 'computer' })
  await sidecar.request('cancel', {})
} catch (error) {
  console.log(JSON.stringify({ ok: false, error: String(error && error.message) }))
  sidecar.dispose()
  process.exit(1)
}
const withJsonRpc = sent.filter((m) => Object.prototype.hasOwnProperty.call(m, 'jsonrpc'))
const ok = sent.length > 0 && withJsonRpc.length === 0
console.log(JSON.stringify({
  ok,
  messages: sent.length,
  withJsonRpc: withJsonRpc.length,
  methods: sent.map((m) => m.method),
  firstKeys: sent.length ? Object.keys(sent[0]).sort() : [],
  sample: sent.length ? sent[0] : null,
}))
sidecar.dispose()
process.exit(ok ? 0 : 1)