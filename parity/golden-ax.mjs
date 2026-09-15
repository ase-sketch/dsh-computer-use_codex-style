// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// R8 golden sample: run the OFFICIAL helper and our helper against the same window and
// diff the accessibility text they report, so the element-index line format is compared
// against the real thing instead of against our own reconstruction.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
const OFFICIAL = codexApp + '/runtimes/cua_node/b58ca2eaa616c2da/bin/node_modules/@oai/cua/bin/windows/codex-computer-use.exe'
const OURS = repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
const OUT = repoRoot + '/parity/golden-ax'
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class Helper {
  constructor(exe, label) {
    this.label = label
    this.raw = []
    // The official helper launches the Codex app-server on startup, so it needs the
    // same environment the plugin's .mcp.json provides.
    const env = { ...process.env }
    env.CODEX_HOME = codexHome
    env.CODEX_CLI_PATH = process.env.CODEX_CLI_PATH || codexApp + '\\bin\\fd4c151a749f3ab4\\codex.exe'
    // A real parent pid, like the plugin passes. With `--parent-pid 0` the official helper
    // cannot open its parent and exits immediately.
    this.c = spawn(exe, ['--parent-pid', String(process.pid)], { stdio: ['pipe', 'pipe', 'pipe'], env })
    this.buf = ''; this.id = 1; this.p = new Map()
    this.c.stdout.setEncoding('utf8')
    this.c.stdout.on('data', (ch) => { this.raw.push(ch); this.buf += ch; let i
      while ((i = this.buf.indexOf(String.fromCharCode(10))) !== -1) {
        const line = this.buf.slice(0, i).trim(); this.buf = this.buf.slice(i + 1)
        if (!line) continue; let m; try { m = JSON.parse(line) } catch { continue }
        const f = this.p.get(m.id); if (f) { this.p.delete(m.id); f(m) } } })
    this.c.stderr.setEncoding('utf8')
    this.c.stderr.on('data', (ch) => { this.raw.push('STDERR: ' + ch) })
  }
  send(method, params = {}, meta = {}) {
    const id = this.id++
    return new Promise((r) => { this.p.set(id, r)
      this.c.stdin.write(JSON.stringify({ id, method, params, meta }) + String.fromCharCode(10))
      setTimeout(() => { if (this.p.delete(id)) r({ ok: false, error: 'TIMEOUT' }) }, 20000) })
  }
  kill() { try { this.c.kill() } catch {} }
}

async function probe(exe, label) {
  const h = new Helper(exe, label)
  const out = { label, alive: true }
  const listed = await h.send('list_windows')
  out.listRaw = JSON.stringify(listed).slice(0, 400)
  const arr = Array.isArray(listed.result) ? listed.result : (listed.result && listed.result.windows) || []
  const target = arr.find((w) => w && typeof w.title === 'string' && w.title.includes('Parity Target'))
  if (!target) { out.error = 'target window not in list_windows'; h.kill(); return out }
  out.target = target
  let meta = { 'x-oai-cua-approved-app': target.app, session_id: 'golden', turn_id: 'turn-1' }
  const request = { window: { app: target.app, id: target.id }, include_text: true, include_screenshot: false }
  let obs = await h.send('get_window_state', request, meta)
  // The official answers an unapproved app with an approval request; retry with the key
  // it asks for, which is its own app identity rather than the list_windows `app`.
  if (obs && obs.ok === false && obs.approvalRequest) {
    out.firstApproval = obs.approvalRequest
    meta = { ...meta, 'x-oai-cua-approved-app': obs.approvalRequest.app }
    obs = await h.send('get_window_state', request, meta)
  }
  out.obsKeys = obs.result ? Object.keys(obs.result).join(',') : JSON.stringify(obs).slice(0, 200)
  const acc = obs.result && obs.result.accessibility
  if (acc && typeof acc === 'object') {
    out.accessibility = acc
    out.tree = acc.tree || ''
    out.focused = acc.focused_element || ''
  } else {
    out.accessibility = String(acc || JSON.stringify(obs).slice(0, 400))
    out.tree = out.accessibility
  }
  out.resultKeys = obs.result ? Object.keys(obs.result).sort().join(',') : 'none'
  // A second observation, this time with a screenshot, to see whether the official
  // only reports element states / bounds on a warmer or screenshot-bearing call.
  const obs2 = await h.send('get_window_state', {
    window: { app: target.app, id: target.id },
    include_text: true,
    include_screenshot: true,
  }, meta)
  const acc2 = obs2.result && obs2.result.accessibility
  out.secondTree = (acc2 && typeof acc2 === 'object' && acc2.tree) || String(obs2.error || 'none')
  h.kill()
  return out
}

// After the first dump, change a value through the official's own set_value and observe
// again: the official answers with a diff, which shows how it reports values and states.
async function probeDiff(exe) {
  const h = new Helper(exe, 'diff')
  const listed = await h.send('list_windows')
  const arr = Array.isArray(listed.result) ? listed.result : []
  const target = arr.find((w) => w && typeof w.title === 'string' && w.title.includes('Parity Target'))
  if (!target) { h.kill(); return 'no target' }
  let meta = { session_id: 'golden', turn_id: 'turn-diff' }
  const window = { app: target.app, id: target.id }
  let obs = await h.send('get_window_state', { window, include_text: true, include_screenshot: false }, meta)
  if (obs && obs.ok === false && obs.approvalRequest) {
    meta = { ...meta, 'x-oai-cua-approved-app': obs.approvalRequest.app }
    obs = await h.send('get_window_state', { window, include_text: true, include_screenshot: false }, meta)
  }
  const set = await h.send('set_value', { window, element_index: 2, value: 'official-diff-probe' }, meta)
  const after = await h.send('get_window_state', { window, include_text: true, include_screenshot: false }, meta)
  const acc = after.result && after.result.accessibility
  h.kill()
  return 'set_value=' + JSON.stringify(set).slice(0, 160) + String.fromCharCode(10) + 'diff observe:' + String.fromCharCode(10) + String((acc && acc.tree) || after.error || 'none')
}

// A second, much richer window: if the official ever prints element states, `Value: ` or
// `Secondary Actions: ` for non-root elements, this window will show it.
async function probeRicher(exe, label) {
  const h = new Helper(exe, label)
  const listed = await h.send('list_windows')
  const arr = Array.isArray(listed.result) ? listed.result : []
  const edge = arr.find((w) => w && typeof w.title === 'string' && /Edge|msedge|MSEdge/i.test(w.app + ' ' + w.title))
  if (!edge) { h.kill(); return { label, tree: 'no edge window' } }
  let meta = { session_id: 'golden', turn_id: 'turn-rich' }
  const request = { window: { app: edge.app, id: edge.id }, include_text: true, include_screenshot: false }
  let obs = await h.send('get_window_state', request, meta)
  if (obs && obs.ok === false && obs.approvalRequest) {
    meta = { ...meta, 'x-oai-cua-approved-app': obs.approvalRequest.app }
    obs = await h.send('get_window_state', request, meta)
  }
  const acc = obs.result && obs.result.accessibility
  h.kill()
  return { label, app: edge.app, tree: (acc && acc.tree) || String(obs.error || 'none') }
}

const results = {}
results.official = await probe(OFFICIAL, 'official')
await sleep(1200)
results.ours = await probe(OURS, 'ours')
await sleep(800)
const diffText = await probeDiff(OFFICIAL)
fs.writeFileSync(path.join(OUT, 'official-diff.txt'), diffText)
console.log('=== official diff after set_value ===')
console.log(diffText.split(String.fromCharCode(10)).slice(0, 20).join(String.fromCharCode(10)))
await sleep(600)
const rich = await probeRicher(OFFICIAL, 'official')
fs.writeFileSync(path.join(OUT, 'official-rich.tree.txt'), String(rich.tree || ''))
console.log('=== richer window probe (official) app=' + rich.app + ' ===')
console.log(String(rich.tree || '').split(String.fromCharCode(10)).slice(0, 26).join(String.fromCharCode(10)))
fs.writeFileSync(path.join(OUT, 'comparison.json'), JSON.stringify(results, null, 2))
for (const key of ['official', 'ours']) {
  const r = results[key]
  fs.writeFileSync(path.join(OUT, key + '.tree.txt'), String(r.tree || r.error || ''))
  fs.writeFileSync(path.join(OUT, key + '.focused.txt'), String(r.focused || ''))
  fs.writeFileSync(path.join(OUT, key + '.windows.json'), String(r.listRaw || ''))
  console.log('=== ' + key + ' ===')
  console.log('target: ' + JSON.stringify(r.target))
  console.log('obsKeys: ' + r.obsKeys)
  console.log('listRaw: ' + String(r.listRaw).slice(0, 220))
  console.log('resultKeys: ' + r.resultKeys)
  console.log('focused: ' + JSON.stringify(r.focused))
  console.log('tree:')
  console.log(String(r.tree || r.error || '').split(String.fromCharCode(10)).slice(0, 24).join(String.fromCharCode(10)))
  if (key === 'official') {
    console.log('accessibility object:')
    console.log(JSON.stringify(r.accessibility).slice(0, 2600))
  }
  if (r.secondTree && r.secondTree !== r.tree) {
    console.log('--- second observation differs ---')
    console.log(String(r.secondTree).split(String.fromCharCode(10)).slice(0, 16).join(String.fromCharCode(10)))
  }
  console.log('')
}