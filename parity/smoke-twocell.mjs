// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// P7: two-cell loop against a real WinForms window, over ONE persistent helper
// process (the observation lease is per-process, like the official helper).
import { spawn } from 'node:child_process'
import fs from 'node:fs'
const EXE = repoRoot + '\\helper-rs\\target\\release\\dsh-computer-use.exe'

class Helper {
  constructor() {
    this.child = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.buf = ''; this.stderr = ''; this.nextId = 1; this.pending = new Map()
    this.child.stderr.on('data', (c) => { this.stderr += String(c) })
    this.child.stdout.setEncoding('utf8')
    this.child.stdout.on('data', (chunk) => {
      this.buf += chunk; let idx
      while ((idx = this.buf.indexOf('\n')) !== -1) {
        const line = this.buf.slice(0, idx).trim(); this.buf = this.buf.slice(idx + 1)
        if (!line) continue
        let msg; try { msg = JSON.parse(line) } catch { continue }
        const p = this.pending.get(msg.id)
        if (p) { this.pending.delete(msg.id); p(msg) }
      }
    })
  }
  call(method, params = {}, meta = {}) {
    const id = this.nextId++
    return new Promise((resolve) => {
      this.pending.set(id, resolve)
      this.child.stdin.write(JSON.stringify({ id, method, params, meta }) + '\n')
      setTimeout(() => { if (this.pending.delete(id)) resolve({ ok: false, error: 'timeout' }) }, 45000)
    })
  }
  kill() { try { this.child.kill() } catch {} }
}

const h = new Helper()
const listReply = await h.call('list_windows')
const list = listReply.result
const target = list.find((w) => w.title === 'Parity Target')
if (!target) { console.log('target not found:', list.map((w) => w.title).join(' | ').slice(0, 300)); h.kill(); process.exit(1) }
console.log('target:', target.app, target.id)
const win = { app: target.app, id: target.id }
const meta = { 'x-oai-cua-approved-app': target.app }

// The UIA monitor can still be starting on the very first observe.
let obs = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: true }, meta)
for (let attempt = 1; obs.ok !== true && attempt <= 5; attempt++) {
  console.log('observe retry', attempt, '->', obs.error)
  await new Promise((r) => setTimeout(r, 1200))
  obs = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: true }, meta)
}
if (obs.ok !== true) { console.log('observe failed:', obs.error); h.kill(); process.exit(1) }
const tree = String(obs.result.accessibility.tree)
const shot = obs.result.screenshots[0]
console.log('screenshot:', shot.id, shot.width + 'x' + shot.height, 'origin', shot.originX + ',' + shot.originY)
fs.writeFileSync(repoRoot + '\\parity\\shot-before.png', Buffer.from(String(shot.url).split(',')[1], 'base64'))

const idxOf = (line) => { const m = line && line.match(/^\s*\[(\d+)\]/); return m ? Number(m[1]) : null }
const lines = tree.split('\n')
const buttonIndex = idxOf(lines.find((l) => l.includes('Parity Button')))
const editIndex = idxOf(lines.find((l) => l.includes('ID: ParityBox')))
console.log('buttonIndex =', buttonIndex, 'editIndex =', editIndex)

const click = await h.call('click', { window: win, element_index: buttonIndex }, meta)
console.log('click(element_index):', click.ok === true ? 'ok' : 'ERROR ' + click.error)

// The click invalidates the observation? No: one action then refresh.
const obs2 = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: true }, meta)
console.log('refresh after click:', obs2.ok === true ? 'ok' : 'ERROR ' + obs2.error)
if (obs2.ok === true) {
  const s2 = obs2.result.screenshots[0]
  if (s2) fs.writeFileSync(repoRoot + '\\parity\\shot-after-click.png', Buffer.from(String(s2.url).split(',')[1], 'base64'))
}

const setv = await h.call('set_value', { window: win, element_index: editIndex, value: 'parity-written-by-dsh' }, meta)
console.log('set_value:', setv.ok === true ? 'ok' : 'ERROR ' + setv.error)

const after = await h.call('get_window_state', { window: win, include_screenshot: false, include_text: true, disableDiffing: true }, meta)
if (after.ok === true) {
  const t2 = String(after.result.accessibility.tree)
  console.log('new text visible in tree:', t2.includes('parity-written-by-dsh'))
  const line = t2.split('\n').find((l) => l.includes('parity-written-by-dsh'))
  console.log('  ', line)
} else { console.log('final observe ERROR', after.error) }

// Coordinate click path: click the text box by window-relative coordinates.
const vp = after.result && after.result.screenshots
const obs3 = await h.call('get_window_state', { window: win, include_screenshot: true, include_text: false }, meta)
if (obs3.ok === true) {
  const s3 = obs3.result.screenshots[0]
  console.log('coord observe shot:', s3.id, s3.width + 'x' + s3.height)
  const r = await h.call('click', { window: win, screenshotId: s3.id, x: 200, y: 150 }, meta)
  console.log('click(screenshotId+x,y):', r.ok === true ? 'ok' : 'ERROR ' + r.error)
  const bad = await h.call('click', { window: win, screenshotId: s3.id, x: 99999, y: 150 }, meta)
  console.log('click(out of bounds):', bad.ok === true ? 'UNEXPECTED ok' : bad.error)
}
h.kill()
if (h.stderr.trim()) console.log('stderr:', h.stderr.trim().slice(0, 300))