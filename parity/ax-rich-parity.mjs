// Derived paths only: no machine-specific absolute path belongs in a tracked script.

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// AX-19..AX-23 live A/B gate: run the OFFICIAL helper and OUR helper (official
// annotations mode) against the same rich window in the same session, and compare the
// accessibility text they report line by line.
//
// Why this gate exists: the older golden-ax gate only compared ParityTarget, whose tree
// carries no element states at all, so it could not see the official's field order,
// control-type casing, non-root states, non-root Secondary Actions or tree-header name
// source. A gate that cannot fail is not a gate (see _verification-log.md V1..V6).
//
// The official helper is launched with a THROWAWAY CODEX_HOME, because the official notify
// rewrite doubles backslashes on every run and once inflated ~/.codex/config.toml to 2.1 GB
// (11-official-sampling.md section 5). Never point this script at the real CODEX_HOME.
import { spawn, execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')
const OUT = path.join(HERE, 'ax-rich')
const OFFICIAL = codexApp + '/runtimes/cua_node/b58ca2eaa616c2da/bin/node_modules/@oai/cua/bin/windows/codex-computer-use.exe'
const OURS = path.join(ROOT, 'helper-rs/target/release/dsh-computer-use.exe')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const argv = process.argv.slice(2)
const flag = (name) => argv.includes('--' + name)
const opt = (name, dflt) => { const i = argv.indexOf('--' + name); return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt }
const TARGET = opt('target', 'auto')
const OFFICIAL_ONLY = flag('official-only')
const OURS_ONLY = flag('ours-only')
const QUIET = flag('quiet')
// --focus brings the target to the foreground first. The official only folds the focused
// sentence into the tree while the window is focused, so this is how the gate covers it.
const FOCUS = flag('focus')

// The official state vocabulary, verbatim from the .rdata run
// `selectableselecteddisabledcollapsedexpandedpartially expandedsettablesettable, stringsettable, float`
// plus `offonindeterminate`. Restricting the token scan to these words keeps names that
// merely contain parentheses from being mistaken for states.
const STATES = ['partially expanded', 'settable, string', 'settable, float', 'selectable', 'selected', 'disabled', 'collapsed', 'expanded', 'settable', 'indeterminate', 'off', 'on']
const STATE_RE = new RegExp('\\(' + STATES.map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + '\\)', 'g')
const count = (text, re) => (text.match(re) || []).length

function makeHome() {
  const dir = path.join(os.tmpdir(), 'dsh-ax-rich-codexhome')
  fs.mkdirSync(dir, { recursive: true })
  const cfg = path.join(dir, 'config.toml')
  if (!fs.existsSync(cfg)) fs.writeFileSync(cfg, '# throwaway home for the AX A/B gate\n')
  if (fs.statSync(cfg).size > 1 << 20) fs.writeFileSync(cfg, '# throwaway home, reset after bloat\n')
  return dir
}

class Helper {
  constructor(exe, env) {
    this.c = spawn(exe, ['--parent-pid', String(process.pid)], { stdio: ['pipe', 'pipe', 'pipe'], env })
    this.buf = ''; this.id = 1; this.p = new Map(); this.err = ''
    this.c.stdout.setEncoding('utf8')
    this.c.stdout.on('data', (ch) => { this.buf += ch; let i
      while ((i = this.buf.indexOf('\n')) !== -1) { const l = this.buf.slice(0, i).trim(); this.buf = this.buf.slice(i + 1); if (!l) continue; let m; try { m = JSON.parse(l) } catch { continue }; const f = this.p.get(m.id); if (f) { this.p.delete(m.id); f(m) } } })
    this.c.stderr.setEncoding('utf8')
    this.c.stderr.on('data', (ch) => { this.err += ch })
  }
  call(method, params = {}, meta = {}, t = 45000) { const id = this.id++
    return new Promise((r) => { this.p.set(id, r); this.c.stdin.write(JSON.stringify({ id, method, params, meta }) + '\n'); setTimeout(() => { if (this.p.delete(id)) r({ ok: false, error: 'TIMEOUT' }) }, t) }) }
  kill() { try { this.c.kill() } catch {} }
}

function pickTarget(list, kind) {
  const s = (v) => String(v == null ? '' : v)
  if (kind === 'word') return list.filter((w) => /WINWORD/i.test(s(w.app)))[0]
  if (kind === 'vscode') return list.filter((w) => /VisualStudioCode/i.test(s(w.app)))[0]
  if (kind === 'explorer') return list.filter((w) => /explorer/i.test(s(w.app)) && s(w.title).length > 0)[0]
  if (kind === 'parity') return list.filter((w) => /Parity Target/i.test(s(w.title)))[0]
  return null
}

// A minimized window is refused identically by both helpers, so un-minimize it (and only
// that: no SetForegroundWindow, no click) before giving up on a comparison.
function restoreWindow(hwnd, focus) {
  try {
    const args = ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(HERE, 'restore-window.ps1'), String(hwnd)]
    if (focus) args.push('-Focus')
    execFileSync('pwsh', args, { stdio: 'ignore', timeout: 15000 })
    return true
  } catch { return false }
}

async function capture(exe, env, kind, label) {
  const h = new Helper(exe, env)
  await sleep(label === 'official' ? 1800 : 1500)
  const listed = await h.call('list_windows')
  const list = Array.isArray(listed.result) ? listed.result : []
  const w = pickTarget(list, kind)
  if (!w) { h.kill(); return { label, ok: false, missing: true, error: 'target ' + kind + ' is not open' } }
  // Un-minimize before asking (never leave a minimized target to chance): the official
  // answers a minimized window inconsistently -- sometimes the documented
  // `window is minimized; call activate_window, ...` error, sometimes `ok:true` with
  // `accessibility: null` -- and either way there is nothing to compare.
  restoreWindow(w.id, FOCUS)
  await sleep(600)
  let meta = { session_id: 'ax-rich-parity', turn_id: 'turn-' + label }
  const request = { window: { app: w.app, id: w.id }, include_text: true, include_screenshot: false }
  let obs = await h.call('get_window_state', request, meta)
  if (obs && obs.ok === false && obs.approvalRequest) {
    meta = Object.assign({}, meta, { 'x-oai-cua-approved-app': obs.approvalRequest.app })
    obs = await h.call('get_window_state', request, meta)
  }
  if (obs && obs.ok === false && /minimized/.test(String(obs.error))) {
    restoreWindow(w.id, FOCUS)
    await sleep(1500)
    obs = await h.call('get_window_state', request, meta)
  } else if (FOCUS) {
    restoreWindow(w.id, true)
    await sleep(900)
    obs = await h.call('get_window_state', request, meta)
  }
  const acc = obs.result && obs.result.accessibility
  const tree = (acc && typeof acc === 'object' && acc.tree) || ''
  h.kill()
  const obsError = obs && obs.error
    ? String(obs.error)
    : (tree ? undefined : 'empty accessibility: ' + JSON.stringify(obs && obs.result && obs.result.accessibility).slice(0, 120) + ' window=' + JSON.stringify(w.title))
  const obj = acc && typeof acc === 'object' ? acc : {}
  // The whole accessibility payload is compared, not just the tree: the official also
  // reports `focused_element` as its own field and decides independently whether to fold a
  // focused sentence and a `Document text:` block into the tree (Word: document text yes,
  // sentence no).
  return {
    label, ok: Boolean(tree), error: obsError, window: w, tree, raw: obs,
    accKeys: Object.keys(obj).sort(),
    focusedElement: obj.focused_element || '',
    // AX-15: the official's `cacheDiagnostics` is exactly three keys. DSH has been returning
    // the whole `diagnostic_state` payload here (model-visible), which no plugin consumes.
    cacheDiagnosticsKeys: (obs.result && obs.result.cacheDiagnostics && typeof obs.result.cacheDiagnostics === 'object')
      ? Object.keys(obs.result.cacheDiagnostics).sort()
      : [],
    documentText: obj.document_text || '',
    meta: obj.meta,
    resultKeys: obs.result ? Object.keys(obs.result).sort() : String(acc),
  }
}

function stats(tree) {
  // Stop at the first blank line: everything after it is a tail section (`Document text:`,
  // `Selected text:`, the focused sentence), not tree lines.
  const all = tree.length ? tree.split('\n') : []
  const cut = all.findIndex((line, i) => i > 0 && line === '')
  const lines = cut > 0 ? all.slice(0, cut) : all
  const roles = {}
  for (const line of lines.slice(1)) {
    const body = line.replace(/^\t+/, '').replace(/^\d+ /, '')
    const role = body.split(' ')[0]
    if (role) roles[role] = (roles[role] || 0) + 1
  }
  const stateTokens = {}
  for (const m of tree.matchAll(STATE_RE)) stateTokens[m[0]] = (stateTokens[m[0]] || 0) + 1
  // A state token that does not sit immediately after the role means the field order is
  // `role name (state)` instead of the official `role (state) name`.
  let misordered = 0
  for (const line of lines.slice(1)) {
    if (!STATE_RE.test(line)) continue
    STATE_RE.lastIndex = 0
    const body = line.replace(/^\t+/, '').replace(/^\d+ /, '')
    const sp = body.indexOf(' ')
    const rest = sp < 0 ? '' : body.slice(sp + 1)
    if (!rest.startsWith('(')) misordered++
  }
  return {
    lines: lines.length, bytes: Buffer.byteLength(tree, 'utf8'),
    states: stateTokens,
    secondary: count(tree, /Secondary Actions:/g),
    descriptions: count(tree, /Description: /g),
    values: count(tree, /Value: /g),
    ids: count(tree, / ID: /g),
    truncated: count(tree, /\(truncated: /g),
    misordered,
    roles,
  }
}

// The tree body is everything before the first blank line; the tail sections after it are
// `The focused UI element is ...`, `Selected:`, `Selected text:` and `Document text:`.
function bodyOf(tree) {
  const lines = tree.length ? tree.split('\n') : []
  const cut = lines.findIndex((line, i) => i > 0 && line === '')
  return (cut > 0 ? lines.slice(0, cut) : lines).join('\n')
}

function tailSections(tree) {
  const lines = tree.length ? tree.split('\n') : []
  const cut = lines.findIndex((line, i) => i > 0 && line === '')
  const tail = cut > 0 ? lines.slice(cut + 1) : []
  return {
    focusedSentence: tail.some((line) => line.startsWith('The focused UI element is ')),
    selectedList: tail.some((line) => line === 'Selected:'),
    selectedText: tail.some((line) => line.startsWith('Selected text:')),
    documentText: tail.some((line) => line.startsWith('Document text:')),
  }
}

// The tail's focused sentence is the *foreground* focus contract: when the target window
// actually holds focus, the official and we both name the same element (this is what the
// historical ParityTarget golden pins). The background case is the AX-24 residual.
function focusedSentenceOf(tree) {
  const line = (tree.length ? tree.split('\n') : []).find((l) => l.startsWith('The focused UI element is '))
  return line || ''
}

function diffLines(a, b) {
  const A = a.split('\n'), B = b.split('\n')
  const out = []
  for (let i = 0; i < Math.max(A.length, B.length); i++) {
    if (A[i] !== B[i]) out.push({ line: i + 1, official: A[i] === undefined ? '<none>' : A[i], ours: B[i] === undefined ? '<none>' : B[i] })
    if (out.length >= 60) break
  }
  return out
}

const kind = TARGET === 'auto' ? 'word' : TARGET
// `--target auto` = Word when it is open, else Explorer (see the fallback below).
fs.mkdirSync(OUT, { recursive: true })
const home = makeHome()
const officialEnv = Object.assign({}, process.env, {
  CODEX_HOME: home,
  CODEX_CLI_PATH: process.env.CODEX_CLI_PATH || codexApp + '/bin/fd4c151a749f3ab4/codex.exe',
})
const oursEnv = Object.assign({}, process.env, { DSH_CU_AX_ANNOTATIONS: 'official' })

let res = {}
const manual = TARGET !== 'auto'
let activeKind = kind
async function runCaptures(k) {
  const out = {}
  if (!OURS_ONLY) out.official = await capture(OFFICIAL, officialEnv, k, 'official')
  if (!OFFICIAL_ONLY) out.ours = await capture(OURS, oursEnv, k, 'ours')
  return out
}
res = await runCaptures(activeKind)
// `auto` prefers Word (a rich window whose tree is stable) and falls back to Explorer, which
// is essentially always open.
if (!manual && ((res.official && res.official.missing) || (res.ours && res.ours.missing))) {
  activeKind = 'explorer'
  res = await runCaptures(activeKind)
}

if (res.official && res.official.tree !== undefined) fs.writeFileSync(path.join(OUT, activeKind + '.official.txt'), res.official.tree)
if (res.ours && res.ours.tree !== undefined) fs.writeFileSync(path.join(OUT, activeKind + '.ours.txt'), res.ours.tree)
for (const side of ['official', 'ours']) {
  const r = res[side]
  if (!r || r.tree === undefined) continue
  fs.writeFileSync(path.join(OUT, activeKind + '.' + side + '.payload.json'), JSON.stringify({
    keys: r.accKeys, resultKeys: r.resultKeys, focused_element: r.focusedElement,
    document_text: r.documentText, meta: r.meta, tree: r.tree,
  }, null, 2))
}
fs.writeFileSync(path.join(OUT, activeKind + '.summary.json'), JSON.stringify({
  kind: activeKind, when: new Date().toISOString(),
  official: res.official ? { ok: res.official.ok, error: res.official.error, window: res.official.window, stats: res.official.tree !== undefined ? stats(res.official.tree) : null } : null,
  ours: res.ours ? { ok: res.ours.ok, error: res.ours.error, window: res.ours.window, stats: res.ours.tree !== undefined ? stats(res.ours.tree) : null } : null,
}, null, 2))

if (OFFICIAL_ONLY || OURS_ONLY) {
  for (const k of Object.keys(res)) { const r = res[k]; console.log(k + ': ok=' + r.ok + ' ' + (r.ok ? JSON.stringify(stats(r.tree)).slice(0, 220) : r.error))
    if (r.ok) console.log('   keys=' + JSON.stringify(r.accKeys) + ' focused=' + JSON.stringify(r.focusedElement) + ' doc=' + JSON.stringify(r.documentText).slice(0, 80)) }
  process.exit(0)
}

const o = res.official, u = res.ours
if (!o.ok || !u.ok) {
  console.log('AX-RICH GATE: cannot compare (' + (o.ok ? '' : 'official: ' + o.error + ' ') + (u.ok ? '' : 'ours: ' + u.error) + ')')
  process.exit(3)
}
const so = stats(o.tree), su = stats(u.tree)
// Hard criteria for the payload: the key set, and whether the two optional text fields are
// present. The *values* of `focused_element` and `document_text` are reported as residuals
// (see AX-24 / AX-27 in 10-GAP-REGISTER.md) because the official's rules for them could not
// be reproduced: for a background window the official reports a provider-tracked last-focused
// control (probed: Word '58 编辑框 字体', Explorer '208 编辑 地址栏 ID: TextBox' while UIA
// reports no keyboard focus anywhere in the window), and its Word document_text is a
// 454-character suffix whose selection rule survived five refuted hypotheses while our
// TextPattern read is the provider's documented DocumentRange.
const keysSame = JSON.stringify(o.accKeys) === JSON.stringify(u.accKeys)
const cacheKeysSame = JSON.stringify(o.cacheDiagnosticsKeys) === JSON.stringify(u.cacheDiagnosticsKeys)
const resultKeysSame = JSON.stringify(o.resultKeys) === JSON.stringify(u.resultKeys)
const docPresence = (o.documentText.length > 0) === (u.documentText.length > 0)
const focusPresence = (o.focusedElement.length > 0) === (u.focusedElement.length > 0)
const valueResiduals = []
if (o.focusedElement !== u.focusedElement) valueResiduals.push('focused_element AX-24: official=' + JSON.stringify(o.focusedElement) + ' ours=' + JSON.stringify(u.focusedElement))
if (o.documentText !== u.documentText) valueResiduals.push('document_text AX-27: official ' + o.documentText.length + ' chars, ours ' + u.documentText.length + ' chars')
const payloadNote = [
  'keys official=' + JSON.stringify(o.accKeys) + ' ours=' + JSON.stringify(u.accKeys) + ' resultKeys official=' + JSON.stringify(o.resultKeys) + ' ours=' + JSON.stringify(u.resultKeys),
  'focused_element official=' + JSON.stringify(o.focusedElement) + ' ours=' + JSON.stringify(u.focusedElement),
  'document_text official=' + JSON.stringify(o.documentText).slice(0, 220) + ' ours=' + JSON.stringify(u.documentText).slice(0, 220),
  'meta official=' + JSON.stringify(o.meta) + ' ours=' + JSON.stringify(u.meta),
].join('\n  ')
const same = bodyOf(o.tree) === bodyOf(u.tree)
const diffs = same ? [] : diffLines(bodyOf(o.tree), bodyOf(u.tree))
const tailO = tailSections(o.tree), tailU = tailSections(u.tree)
const tailSame = JSON.stringify(tailO) === JSON.stringify(tailU)
const focusSentO = focusedSentenceOf(o.tree), focusSentU = focusedSentenceOf(u.tree)
const focusSentenceSame = focusSentO === focusSentU
const officialOnlyRoles = Object.keys(so.roles).filter((r) => !(r in su.roles))
const oursOnlyRoles = Object.keys(su.roles).filter((r) => !(r in so.roles))
const lowercased = officialOnlyRoles.filter((r) => oursOnlyRoles.some((x) => x === r.toLowerCase()))

if (!QUIET) {
  console.log('target=' + activeKind + ' window=' + JSON.stringify(o.window && o.window.title))
  console.log('official: ' + JSON.stringify(so))
  console.log('ours    : ' + JSON.stringify(su))
  console.log('roles official-only=' + JSON.stringify(officialOnlyRoles) + ' ours-only=' + JSON.stringify(oursOnlyRoles) + ' lowercased-pairs=' + JSON.stringify(lowercased))
  console.log('tree-body-identical=' + same + ' differing-body-lines=' + diffs.length + '(capped 60)')
  console.log('tail-sections-identical=' + tailSame + ' official=' + JSON.stringify(tailO) + ' ours=' + JSON.stringify(tailU))
  console.log('focused-sentence-identical=' + focusSentenceSame + ' official=' + JSON.stringify(focusSentO) + ' ours=' + JSON.stringify(focusSentU))
  console.log('payload keys-identical=' + keysSame + ' document_text-present-parity=' + docPresence + ' focused_element-present-parity=' + focusPresence)
  console.log('cacheDiagnostics-keys-identical=' + cacheKeysSame + ' official=' + JSON.stringify(o.cacheDiagnosticsKeys) + ' ours=' + JSON.stringify(u.cacheDiagnosticsKeys))
  console.log('result-keys-identical=' + resultKeysSame + ' official=' + JSON.stringify(o.resultKeys) + ' ours=' + JSON.stringify(u.resultKeys))
  console.log('  ' + payloadNote)
  for (const r of valueResiduals) console.log('  RESIDUAL ' + r)
  for (const d of diffs) console.log('  L' + d.line + '\n    OFF ' + d.official + '\n    OUR ' + d.ours)
}
const failures = []
if (!same) failures.push('tree bodies differ on ' + diffs.length + ' line(s)')
if (!tailSame) failures.push('tail sections differ: official=' + JSON.stringify(tailO) + ' ours=' + JSON.stringify(tailU))
// Only a hard failure when both sides printed a sentence: the official printing none for a
// document-text window is AX-26, covered by the tail-section criterion above.
// The sentence is only a *contract* while the target window holds focus. With the window in
// the background the official names a provider-tracked last-focused control that we cannot
// reproduce (AX-24), and it suppresses the sentence entirely when the tree carries document
// text (AX-26) -- so the sentence is compared strictly only for a `--focus` run.
if (FOCUS && focusSentO && focusSentU && !focusSentenceSame) failures.push('focused sentence differs: official=' + JSON.stringify(focusSentO) + ' ours=' + JSON.stringify(focusSentU))
if (su.misordered > 0) failures.push('field order: ' + su.misordered + ' state token(s) not directly after the role')
if (lowercased.length) failures.push('control-type casing: ' + JSON.stringify(lowercased))
if (su.truncated > so.truncated) failures.push('ours truncates (' + su.truncated + ') where the official does not (' + so.truncated + ')')
if (JSON.stringify(su.states) !== JSON.stringify(so.states)) failures.push('state token counts differ')
if (su.secondary !== so.secondary) failures.push('Secondary Actions count ' + su.secondary + ' != ' + so.secondary)
if (!keysSame) failures.push('accessibility key set differs')
if (!docPresence) failures.push('document_text presence differs')
if (!focusPresence) failures.push('focused_element presence differs')
// AX-15: model-visible schema parity for the cache diagnostics object.
if (!cacheKeysSame) failures.push('cacheDiagnostics key set differs: official=' + JSON.stringify(o.cacheDiagnosticsKeys) + ' ours=' + JSON.stringify(u.cacheDiagnosticsKeys))
// AX-15: the model-visible top-level key set of get_window_state.
if (!resultKeysSame) failures.push('result key set differs: official=' + JSON.stringify(o.resultKeys) + ' ours=' + JSON.stringify(u.resultKeys))
if (su.descriptions !== so.descriptions) failures.push('Description count ' + su.descriptions + ' != ' + so.descriptions)
if (su.values !== so.values) failures.push('Value count ' + su.values + ' != ' + so.values)
if (failures.length) { console.log('AX-RICH GATE: FAIL'); for (const f of failures) console.log('  - ' + f); process.exit(1) }
console.log('AX-RICH GATE: PASS (' + so.lines + ' official lines, tree body byte-identical' + (valueResiduals.length ? ', ' + valueResiduals.length + ' documented residual(s)' : '') + ')')
process.exit(0)