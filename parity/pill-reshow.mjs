/**
 * The status pill must come back after a hide.
 *
 * The existing overlay gates prove the synthetic cursor and the system-cursor
 * suppression survive a hide -> show cycle; none of them looks at the pill itself.
 * That gap shipped a real bug: hiding the overlay windows with SW_HIDE / HWND_BOTTOM
 * drops the layered surface (ULW) and the composition content (DComp), so the next
 * show consumed a window that is visible, topmost and painted -- and rendered nothing.
 * The operator sees the cursor and no pill, which is invisible to a counter-only gate.
 *
 * This gate drives the real helper, hides the overlay with the same cancel the plugin
 * sends at turn end, shows it again, and measures the accent pixels the pill puts on
 * the primary screen. It needs a visible "Parity Target" window and a desktop session,
 * exactly like the other parity probes.
 *
 *   node --import tsx/esm parity/pill-reshow.mjs
 */
import { spawn, execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const pluginRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const candidates = [
  path.join(pluginRoot, 'helper-rs', 'target', 'release', 'dsh-computer-use.exe'),
  path.join(pluginRoot, 'helper-rs', 'bin', 'win32-x64', 'dsh-computer-use.exe'),
]
const exe = candidates.find(candidate => fs.existsSync(candidate))
if (exe === undefined) {
  console.log('SKIP pill-reshow: no helper binary found in ' + candidates.join(' or '))
  process.exit(0)
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
let failures = 0
const gate = (name, ok, evidence) => {
  if (!ok) failures += 1
  console.log((ok ? 'PASS' : 'FAIL') + ' ' + name + (evidence === undefined ? '' : '  ' + evidence))
}

const COUNT = [
  'Add-Type -AssemblyName System.Windows.Forms',
  'Add-Type -AssemblyName System.Drawing',
  '$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds',
  '$strip=New-Object System.Drawing.Bitmap($b.Width,300)',
  '$g=[System.Drawing.Graphics]::FromImage($strip)',
  '$g.CopyFromScreen($b.X,$b.Y,0,0,(New-Object System.Drawing.Size($b.Width,300)))',
  '$n=0',
  'for($y=0;$y -lt 300;$y++){ for($x=0;$x -lt $b.Width;$x++){ $p=$strip.GetPixel($x,$y); if($p.B -gt 150 -and $p.R -lt 130 -and $p.G -gt 90 -and $p.G -lt 215){$n++} } }',
  'Write-Output ("{0} {1}" -f $n,$b.Width)',
].join('; ')
const accent = () => {
  const [count, width] = String(execFileSync('pwsh', ['-NoProfile', '-Command', COUNT], { encoding: 'utf8' })).trim().split(/\s+/)
  return { count: Number(count), width: Number(width) }
}

class Helper {
  constructor() {
    this.child = spawn(exe, ['--parent-pid', '0'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, DSH_CU_OVERLAY_CAPTURABLE: '1' },
    })
    this.buffer = ''
    this.id = 1
    this.pending = new Map()
    this.child.stdout.setEncoding('utf8')
    this.child.stdout.on('data', chunk => {
      this.buffer += chunk
      let index
      while ((index = this.buffer.indexOf('\n')) !== -1) {
        const line = this.buffer.slice(0, index).trim()
        this.buffer = this.buffer.slice(index + 1)
        if (!line) continue
        let message
        try { message = JSON.parse(line) } catch { continue }
        const resolve = this.pending.get(message.id)
        if (resolve) { this.pending.delete(message.id); resolve(message) }
      }
    })
    this.child.stderr.setEncoding('utf8')
    this.child.stderr.on('data', () => {})
  }

  call(method, params = {}, meta = {}) {
    const id = this.id++
    return new Promise(resolve => {
      this.pending.set(id, resolve)
      this.child.stdin.write(JSON.stringify({ id, method, params, meta }) + '\n')
      setTimeout(() => { if (this.pending.delete(id)) resolve({ ok: false, error: 'timeout' }) }, 25000)
    })
  }

  kill() { try { this.child.kill() } catch { /* already gone */ } }
}

const helper = new Helper()
const listed = (await helper.call('list_windows')).result
const target = Array.isArray(listed) ? listed.find(item => item.title === 'Parity Target') : undefined
if (target === undefined) {
  console.log('SKIP pill-reshow: the Parity Target window is not open')
  helper.kill()
  process.exit(0)
}
const win = { app: target.app, id: target.id }
const meta = { 'x-oai-cua-approved-app': target.app }
const show = async () => {
  const state = await helper.call('get_window_state', { window: win, include_screenshot: true }, meta)
  const shot = state.result && state.result.screenshots ? state.result.screenshots[0] : undefined
  if (shot === undefined) throw new Error('no screenshot: ' + JSON.stringify(state).slice(0, 200))
  await helper.call('click', { window: win, screenshotId: shot.id, x: 184, y: 239 }, meta)
}
const overlayState = async () => {
  const diagnostics = await helper.call('diagnostic_state')
  return diagnostics.result && diagnostics.result.overlayState ? diagnostics.result.overlayState : {}
}

const baseline = accent()
await show()
await sleep(700)
const first = accent()
const afterFirst = await overlayState()
gate(
  'pill: the first show puts the pill on screen',
  first.count - baseline.count >= Math.max(8000, first.width * 8),
  'accent ' + baseline.count + ' -> ' + first.count,
)

await helper.call('cancel', {})
await sleep(1300)
const hidden = accent()
gate(
  'pill: cancel takes it off screen again',
  Math.abs(hidden.count - baseline.count) <= Math.max(2000, baseline.count * 0.05),
  'accent ' + hidden.count,
)

await show()
await sleep(900)
const second = accent()
const afterSecond = await overlayState()
gate(
  'pill: a later show puts it back on screen',
  second.count - baseline.count >= Math.max(8000, second.width * 8),
  'accent ' + baseline.count + ' -> ' + second.count,
)
gate(
  'pill: the blanked overlay was rebuilt instead of reused',
  (afterSecond.recreates || 0) > (afterFirst.recreates || 0),
  'recreates ' + (afterFirst.recreates || 0) + ' -> ' + (afterSecond.recreates || 0),
)

helper.kill()
console.log('pill-reshow: ' + (failures === 0 ? 'all gates pass' : failures + ' gate(s) failed'))
process.exit(failures === 0 ? 0 : 1)
