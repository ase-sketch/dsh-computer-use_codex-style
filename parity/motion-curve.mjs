// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// R1: measure the cosmetic cursor's real motion against the official *measured*
// settle table instead of eyeballing a recording or fitting the refuted binary
// polynomial.
//
// The official cursor is a full-screen ULW layer (CodexComputerUseCursorOverlay).
// Its motion was sampled externally with a PrintWindow centroid at ~30 Hz
// (analysis/deep-dive/11-official-sampling.md section 3). That gives, per chord
// length and direction, a settle interval (+/-40 ms), a reverse pre-move
// (backswing) and a perpendicular bow ratio. This script replays the exact
// official (dx, dy) vectors inside ParityTarget and asserts the helper reproduces
// those features. The measured truth lives in parity/official-constants.json
// (cursorMotion.samples), so the geometry table here only carries coordinates.
//
// Each measurement gets a fresh helper process: the sampling report found that one
// long-lived helper stops answering after a few actions (11-official-sampling.md
// section 5.1), so reusing one process made the gate flake instead of fail. A whole
// case is retried when a click is refused or the motion never starts, because under
// the full verify-all load the target can lose foreground between the park and the
// measured click.
//
// A run that never animated, that was refused by a foreground lock, that lost the
// helper, or that ran against a viewport too small for the geometry must never
// overwrite the evidence file.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
const EXE = repoRoot + '/helper-rs/target/release/dsh-computer-use.exe'
const CONSTANTS = repoRoot + '/parity/official-constants.json'
const OUT = path.join(repoRoot + '/parity', 'motion-curve.json')
const NL = String.fromCharCode(10)

class H {
  constructor() {
    this.c = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.buf = ''; this.id = 1; this.p = new Map()
    this.c.stdout.setEncoding('utf8')
    this.c.stdout.on('data', (ch) => { this.buf += ch; let i
      while ((i = this.buf.indexOf(NL)) !== -1) {
        const l = this.buf.slice(0, i).trim(); this.buf = this.buf.slice(i + 1)
        if (!l) continue; let m; try { m = JSON.parse(l) } catch { continue }
        const f = this.p.get(m.id); if (f) { this.p.delete(m.id); f(m) } } })
  }
  call(method, params = {}, meta = {}) {
    const id = this.id++
    return new Promise((r) => { this.p.set(id, r)
      this.c.stdin.write(JSON.stringify({ id, method, params, meta }) + NL)
      setTimeout(() => { if (this.p.delete(id)) r({ ok: false, error: 'timeout' }) }, 45000) })
  }
  kill() { try { this.c.kill() } catch {} }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const constants = JSON.parse(fs.readFileSync(CONSTANTS, 'utf8'))
const measured = new Map(constants.cursorMotion.samples.map((s) => [s.label, s]))

// Exact official window coordinates (E:/Temp/motion3/events.json and
// motion4/events.json, the runs behind section 3). x,y are window-internal px.
const GEOMETRY = [
  ['d0', 300, 300, 300, 300],
  ['d80', 300, 300, 380, 300],
  ['d120', 300, 300, 420, 300],
  ['d180', 300, 300, 480, 300],
  ['d269', 300, 300, 500, 480],
  ['d400', 100, 150, 500, 150],
  ['d613', 60, 140, 640, 340],
  ['d760', 80, 500, 840, 500],
  ['d898', 60, 140, 920, 400],
  ['d998', 40, 40, 880, 580],
]
const OFFICIAL_W = 938, OFFICIAL_H = 619
const SINGLE_SEGMENT_MAX_PX = constants.cursorMotion.singleSegmentMaxPx

// The official window-internal coordinates are 1:1 physical pixels, so the official
// (dx, dy) vectors are reproduced whatever the window size is; all that is required
// is that every click lands inside the captured rect.
const maxX = Math.max(...GEOMETRY.map(([, a, b, c, d]) => Math.max(a, c)))
const maxY = Math.max(...GEOMETRY.map(([, a, b, c, d]) => Math.max(b, d)))

async function connect() {
  const h = new H()
  // A fresh turn scope. The default scope can carry an interrupt flag left by
  // another run (verify-all's own esc test writes one), which refuses every
  // action with the official physical-Escape sentence. A new turn is exactly how
  // a new turn is isolated from the previous one.
  h.meta = { conversationId: 'motion-gate', turnId: 'motion-gate-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8) }
  const listed = await h.call('list_windows', {}, h.meta)
  if (listed.ok !== true || !listed.result) { console.error('connect: list_windows failed ' + JSON.stringify(listed).slice(0, 200)); h.kill(); return null }
  const t = listed.result.find((w) => w.title === 'Parity Target')
  if (!t) { console.error('connect: Parity Target missing among ' + listed.result.map((w) => w.title).join(' | ').slice(0, 300)); h.kill(); return null }
  const win = { app: t.app, id: t.id }
  const meta = { 'x-oai-cua-approved-app': t.app, ...h.meta }
  const obs = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
  if (obs.ok !== true || !obs.result || !obs.result.screenshots || !obs.result.screenshots.length) { console.error('connect: observe failed ' + JSON.stringify(obs).slice(0, 300)); h.kill(); return null }
  return { h, win, meta, shot: obs.result.screenshots[0] }
}

// A dead helper makes h.call resolve without a result; returning null lets every
// polling loop stop cleanly instead of throwing a TypeError mid-gate.
async function overlayState(h) {
  const r = await h.call('diagnostic_state', {}, h.meta || {})
  if (r.ok !== true || !r.result) return null
  return r.result.overlayState
}
async function waitIdle(h, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let idle = 0
  while (Date.now() < deadline) {
    const d = await overlayState(h)
    if (d === null) return null
    if (d.motionActive) { idle = 0 } else { idle++; if (idle >= 2) return d }
  }
  return null
}

// Park at a known origin and *verify* it. The first click of a fresh helper
// process does not move the cursor, and an unverified park made the first case
// measure a 600-1500 px move instead of its intended length.
async function parkAt(s, px, py) {
  const target = { x: s.shot.originX + px, y: s.shot.originY + py }
  let state = null
  for (let attempt = 0; attempt < 3; attempt++) {
    const parked = await s.h.call('click', { window: s.win, screenshotId: s.shot.id, x: px, y: py }, s.meta)
    if (parked.ok !== true) console.error('park click refused: ' + JSON.stringify(parked).slice(0, 200))
    if (await waitIdle(s.h, 15000) === null && state === null) return null
    await sleep(250)
    state = await overlayState(s.h)
    if (state === null) return null
    if (Math.hypot(state.cursorScreenX - target.x, state.cursorScreenY - target.y) <= 1.5) return state
    console.error('park attempt ' + (attempt + 1) + ' for ' + px + ',' + py + ' landed at ' +
      state.cursorScreenX + ',' + state.cursorScreenY + ' (want ' + target.x + ',' + target.y + ')')
  }
  return state
}

// One measurement. Returns the result object without printing, plus a `retry`
// marker when the sample is unusable because of a transient refusal; the wrapper
// decides whether to retry or to publish the line.
async function attemptOnce(label, x0, y0, x1, y1) {
  const m = measured.get(label)
  const s = await connect()
  if (s === null) return { label, retry: 'no-helper' }
  try {
    const parked = await parkAt(s, x0, y0)
    if (parked === null) return { label, retry: 'no-helper' }
    const t0 = Date.now()
    // Poll concurrently with the click so the very first frames (the backswing) are
    // observed: awaiting the click response first let the first poll land after the
    // reverse pre-move had already finished for the longest diagonal move.
    const movePromise = s.h.call('click', { window: s.win, screenshotId: s.shot.id, x: x1, y: y1 }, s.meta)
    const samples = []
    let idle = 0
    for (let i = 0; i < 6000; i++) {
      const d = await overlayState(s.h)
      if (d === null) return { label, retry: 'no-helper' }
      samples.push({ t: Date.now() - t0, x: d.cursorScreenX, y: d.cursorScreenY, tick: d.motionTick, active: d.motionActive, modelMs: d.motionDurationMs })
      if (d.motionActive) { idle = 0 } else { idle++; if (idle >= 4) break }
    }
    const moved = await movePromise
    const refused = moved.ok !== true
    if (refused) console.error('measured click refused: ' + JSON.stringify(moved).slice(0, 200))
    const target = { x: s.shot.originX + x1, y: s.shot.originY + y1 }
    const start = { x: parked.cursorScreenX, y: parked.cursorScreenY }
    const active = samples.filter((v) => v.active)
    const first = active.length ? active[0] : samples[0]
    const last = active.length ? active[active.length - 1] : samples[samples.length - 1]
    const duration = last.t - first.t
    const dx = target.x - start.x
    const dy = target.y - start.y
    const len = Math.hypot(dx, dy)
    let bulge = 0
    let minAlong = 0
    if (len > 0.5) {
      minAlong = Infinity
      for (const v of active) {
        const rx = v.x - start.x, ry = v.y - start.y
        const cross = Math.abs(rx * dy - ry * dx) / len
        if (cross > bulge) bulge = cross
        const along = (rx * dx + ry * dy) / len
        if (along < minAlong) minAlong = along
      }
      if (!Number.isFinite(minAlong)) minAlong = 0
    }
    const settled = samples[samples.length - 1]
    const landedErr = Math.hypot(settled.x - target.x, settled.y - target.y)
    const ratio = len > 0.5 ? bulge / len : 0
    const modelMs = samples.length ? samples[samples.length - 1].modelMs : 0
    const single = len <= SINGLE_SEGMENT_MAX_PX
    const snap = m.tSettleMaxMs === 0 && m.tSettleMinMs === 0
    if (refused || (!snap && active.length === 0)) {
      return { label, retry: refused ? 'click-refused' : 'no-motion', landedErrPx: Number(landedErr.toFixed(2)), frames: active.length }
    }

    // Feature gates. The wall duration gets a +60 ms allowance for the poll
    // round-trip after the animation ends; the exact model duration does not.
    const wallOk = snap ? duration < 60 : (duration >= m.tSettleMinMs - 20 && duration <= m.tSettleMaxMs + 60)
    const modelOk = snap ? true : (modelMs >= m.tSettleMinMs && modelMs <= m.tSettleMaxMs)
    const bowOk = snap ? bulge < 3 : (single ? ratio <= 0.012 : (ratio >= 0.045 && ratio <= 0.145))
    const backOk = snap ? true : (single ? minAlong > -1.5 : minAlong <= -10)
    const landOk = landedErr <= 1.5
    return { label, straight: Math.round(len), officialL: m.L, frames: active.length, durationMs: duration,
      tMin: m.tSettleMinMs, tMax: m.tSettleMaxMs, modelDurationMs: modelMs,
      bulgePx: Number(bulge.toFixed(2)), bulgeRatio: Number(ratio.toFixed(4)),
      backswingPx: Number(minAlong.toFixed(2)), landedErrPx: Number(landedErr.toFixed(2)),
      pass: wallOk && modelOk && bowOk && backOk && landOk, single, snap, pollSamples: samples.length }
  } finally { s.h.kill() }
}

function printResult(r) {
  if (r.invalid) {
    console.error('INVALID ' + r.label + ': ' + r.invalid + (r.landedErrPx !== undefined ? ' landedErr=' + r.landedErrPx + 'px' : ''))
    return
  }
  const range = r.snap ? '[0,0]' : '[' + r.tMin + ',' + r.tMax + ']'
  console.log((r.pass ? '[PASS]' : '[FAIL]') + ' motion ' + r.label +
    ': straight=' + r.straight + 'px officialL=' + r.officialL + 'px frames=' + r.frames +
    ' wallDuration=' + r.durationMs + 'ms ' + range + ' modelDuration=' + r.modelDurationMs + 'ms' +
    ' bulge=' + r.bulgePx + 'px ratio=' + r.bulgeRatio + ' backswing=' + r.backswingPx + 'px' +
    ' landedErr=' + r.landedErrPx + 'px pollSamples=' + r.pollSamples)
}

async function sampleMotion(label, x0, y0, x1, y1) {
  let last = { label, invalid: 'no-attempt' }
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await attemptOnce(label, x0, y0, x1, y1)
    if (!r.retry) { printResult(r); return r }
    last = { label, invalid: r.retry, landedErrPx: r.landedErrPx }
    console.error('retry ' + label + ' (' + (attempt + 1) + '/3): ' + r.retry)
  }
  printResult(last)
  return last
}

// Precheck: the geometry table must agree with the measured sample table, and the
// viewport must be large enough. Both are real drift gates.
const geometryErrors = []
for (const [label, x0, y0, x1, y1] of GEOMETRY) {
  const m = measured.get(label)
  if (!m) { geometryErrors.push(label + ': no measured row'); continue }
  const dx = x1 - x0, dy = y1 - y0
  if (Math.abs(m.dx - dx) > 0.5 || Math.abs(m.dy - dy) > 0.5) {
    geometryErrors.push(label + ': geometry (' + dx + ',' + dy + ') != measured (' + m.dx + ',' + m.dy + ')')
  }
}
if (geometryErrors.length) {
  for (const e of geometryErrors) console.log('GEOMETRY_DRIFT ' + e)
  console.log('geometry table and official-constants.json disagree; ' + OUT + ' left untouched')
  process.exit(2)
}
const probe = await connect()
if (probe === null) {
  console.log('TARGET_MISSING or OBSERVE_FAILED; run parity/raise-target.ps1 first')
  process.exit(1)
}
console.log('viewport=' + probe.shot.width + 'x' + probe.shot.height + ' (official sampling used ' + OFFICIAL_W + 'x' + OFFICIAL_H + ')')
const tooSmall = probe.shot.width <= maxX + 8 || probe.shot.height <= maxY + 8
probe.h.kill()
if (tooSmall) {
  console.log('VIEWPORT_TOO_SMALL cannot hold the official geometry (' + (maxX + 8) + 'x' + (maxY + 8) + ' needed)')
  console.log('run parity/raise-target.ps1 first; ' + OUT + ' left untouched')
  process.exit(2)
}

const results = []
for (const [label, x0, y0, x1, y1] of GEOMETRY) {
  results.push(await sampleMotion(label, x0, y0, x1, y1))
}

// A run that never animated (a refused click that survived the retries, a lost
// helper) must not overwrite the evidence file with 7 ms durations and 500 px
// landing errors, which then read as a product regression.
const invalid = results.filter((r) => r.invalid)
if (invalid.length > 0) {
  console.error('measurement invalid (' + invalid.length + '/' + results.length + ' cases); ' + OUT + ' left untouched')
  process.exit(2)
}

// check-claims C7 reads this file and needs the four legacy labels in a strictly
// increasing distance order. They are the measured d120/d269/d400/d760 moves.
const legacy = { small: 'd120', short: 'd269', medium: 'd400', long: 'd760' }
const curve = Object.entries(legacy).map(([name, src]) => {
  const r = results.find((x) => x.label === src)
  return { label: name, source: src, straight: r.straight, frames: r.frames,
    durationMs: r.durationMs, bulgePx: r.bulgePx, bulgeRatio: r.bulgeRatio,
    landedErrPx: r.landedErrPx, pollSamples: r.pollSamples }
})
fs.writeFileSync(OUT, JSON.stringify(curve, null, 2))
console.log('saved ' + OUT)

const failed = results.filter((r) => !r.pass)
if (failed.length > 0) {
  console.log('official measured gate: ' + (results.length - failed.length) + '/' + results.length +
    ' cases hold; RED = ' + failed.map((r) => r.label).join(', '))
  process.exit(2)
}
console.log('official measured gate: ' + results.length + '/' + results.length + ' cases hold')
