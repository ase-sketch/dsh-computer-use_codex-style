/**
 * The status pill must stay out of the model's screenshots without leaving the
 * operator's screen.
 *
 * The pill is excluded from capture two ways, and the default one exists because the
 * other broke in production:
 *
 *   mask (default) - the compositor drops the pill's root opacity for the duration of one
 *                    capture, so the composed frame never contains it. The operator
 *                    still sees the pill before and after the capture.
 *   wda            - SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) on the pill window
 *                    (official-style). On 2026-09-15 this made the DWM stop presenting
 *                    the DirectComposition content *on screen* as well: the operator saw
 *                    the fake cursor and no pill while every overlay API reported
 *                    visible=true. Hence opt-in, and hence this gate measures both sides.
 *
 * The gate drives the real helper and measures pixels, because that is the only thing
 * that distinguishes "the pill was drawn and hidden for the frame" from "the pill was
 * never drawn at all".
 *
 *   node --import tsx/esm parity/pill-capture-mask.mjs
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
  console.log('SKIP pill-capture-mask: no helper binary found in ' + candidates.join(' or '))
  process.exit(0)
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
let failures = 0
const gate = (name, ok, evidence) => {
  if (!ok) failures += 1
  console.log((ok ? 'PASS' : 'FAIL') + ' ' + name + (evidence === undefined ? '' : '  ' + evidence))
}

const SCREEN_ACCENT = [
  'Add-Type -AssemblyName System.Windows.Forms',
  'Add-Type -AssemblyName System.Drawing',
  '$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds',
  '$strip=New-Object System.Drawing.Bitmap($b.Width,400)',
  '$g=[System.Drawing.Graphics]::FromImage($strip)',
  '$g.CopyFromScreen($b.X,$b.Y,0,0,(New-Object System.Drawing.Size($b.Width,400)))',
  '$n=0',
  'for($y=0;$y -lt 400;$y++){ for($x=0;$x -lt $b.Width;$x++){ $p=$strip.GetPixel($x,$y); if($p.B -gt 150 -and $p.R -lt 130 -and $p.G -gt 90 -and $p.G -lt 215){$n++} } }',
  'Write-Output ("{0} {1}" -f $n,$b.Width)',
].join('; ')
const screenAccent = () => {
  const [count, width] = String(execFileSync('pwsh', ['-NoProfile', '-Command', SCREEN_ACCENT], { encoding: 'utf8' })).trim().split(/\s+/)
  return { count: Number(count), width: Number(width) }
}
/** Accent pixels inside a saved screenshot, so the frame the model would read is measured. */
const fileAccent = file => {
  const escaped = file.replace(/\\/g, '\\\\')
  const ps = [
    'Add-Type -AssemblyName System.Drawing',
    '$b=[System.Drawing.Image]::FromFile("' + escaped + '")',
    '$n=0',
    'for($y=0;$y -lt $b.Height;$y++){ for($x=0;$x -lt $b.Width;$x++){ $p=$b.GetPixel($x,$y); if($p.B -gt 150 -and $p.R -lt 130 -and $p.G -gt 90 -and $p.G -lt 215){$n++} } }',
    'Write-Output $n',
  ].join('; ')
  return Number(String(execFileSync('pwsh', ['-NoProfile', '-Command', ps], { encoding: 'utf8' })).trim())
}

class Helper {
  constructor(env) {
    this.child = spawn(exe, ['--parent-pid', '0'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, ...env },
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

/** Park the target window over the top-centre of the primary screen, where the pill is. */
function parkTarget() {
  const bounds = String(execFileSync('pwsh', ['-NoProfile', '-Command',
    'Add-Type -AssemblyName System.Windows.Forms; $b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; Write-Output ($b.X.ToString() + " " + $b.Y.ToString() + " " + $b.Width.ToString())',
  ], { encoding: 'utf8' })).trim().split(/\s+/)
  const [x, y, width] = bounds.map(Number)
  const w = Math.min(1200, width)
  const left = x + Math.floor((width - w) / 2)
  return String(execFileSync('pwsh', ['-NoProfile', '-File', path.join(pluginRoot, 'parity', 'move-target.ps1'),
    String(left), String(y), String(w), '600'], { encoding: 'utf8' })).trim()
}

const saveShot = (shot, file) => {
  const match = /base64,(.*)$/s.exec(String(shot.url || ''))
  if (!match) throw new Error('screenshot has no data url')
  fs.writeFileSync(file, Buffer.from(match[1], 'base64'))
}

/**
 * One full pass: park the target, show the overlay, capture the window, and report the
 * pixels on the screen and inside the frame.
 */
async function run(gatePrefix, env) {
  console.log('-- ' + gatePrefix + ' with ' + JSON.stringify(env))
  console.log('   ' + parkTarget())
  await sleep(900)
  const helper = new Helper(env)
  try {
    const listed = await helper.call('list_windows')
    const target = (listed.result || []).find(item => item && item.title === 'Parity Target')
    if (target === undefined) {
      console.log('SKIP pill-capture-mask: the Parity Target window is not open')
      return undefined
    }
    const win = { app: target.app, id: target.id }
    const meta = { 'x-oai-cua-approved-app': target.app }
    const firstResult = await helper.call('get_window_state', { window: win, include_screenshot: true }, meta)
    const first = firstResult?.result?.screenshots?.[0]
    if (first === undefined) {
      // A locked or windowless desktop makes every observation fail ("foreground window
      // did not report a process id"); that is an environment, not a product, failure.
      console.log('SKIP pill-capture-mask: ' + (firstResult?.error || 'the window produced no screenshot') +
        ' (needs an unlocked desktop and a visible Parity Target)')
      return undefined
    }
    saveShot(first, path.join(pluginRoot, 'parity', 'pill-mask-before.jpg'))
    const beforeFrame = fileAccent(path.join(pluginRoot, 'parity', 'pill-mask-before.jpg'))

    await helper.call('click', { window: win, screenshotId: first.id, x: 184, y: 239 }, meta)
    await sleep(900)
    const state = (await helper.call('diagnostic_state')).result.overlayState
    const onScreen = screenAccent()

    const afterResult = await helper.call('get_window_state', { window: win, include_screenshot: true }, meta)
    const after = afterResult?.result?.screenshots?.[0]
    if (after === undefined) {
      throw new Error('the masked capture produced no screenshot: ' + (afterResult?.error || 'unknown'))
    }
    saveShot(after, path.join(pluginRoot, 'parity', 'pill-mask-after.jpg'))
    const afterFrame = fileAccent(path.join(pluginRoot, 'parity', 'pill-mask-after.jpg'))

    const masked = (await helper.call('diagnostic_state')).result.overlayState
    const stillOnScreen = screenAccent()
    await helper.call('cancel', {})
    await sleep(600)
    const hidden = screenAccent()
    return {
      exclusion: state.captureExclusion,
      beforeFrame,
      afterFrame,
      onScreen,
      stillOnScreen,
      hidden,
      maskCount: (masked.captureMaskCount || 0) - (state.captureMaskCount || 0),
      maskedAfter: masked.captureMasked,
    }
  } finally {
    helper.kill()
    await sleep(1200)
  }
}

const pillIsOnScreen = sample => sample.onScreen.count - sample.hidden.count >= Math.max(8000, sample.onScreen.width * 4)

// 1. The default: mask.
const masked = await run('default exclusion', {})
if (masked === undefined) {
  process.exit(0)
}
gate('mask: the mode is the on-screen-safe default', masked.exclusion === 'mask', 'exclusion ' + masked.exclusion)
gate('mask: the operator still sees the pill after a capture',
  pillIsOnScreen(masked),
  'screen ' + masked.hidden.count + ' (hidden) -> ' + masked.onScreen.count + ' (shown) -> ' + masked.stillOnScreen.count + ' (after the capture)')
gate('mask: the captured frame does not contain the pill',
  masked.afterFrame - masked.beforeFrame <= Math.max(300, masked.beforeFrame * 0.25),
  'frame accent ' + masked.beforeFrame + ' -> ' + masked.afterFrame)
gate('mask: the mask was requested during the capture', masked.maskCount >= 1, 'captureMaskCount +' + masked.maskCount)
gate('mask: the mask is lifted again afterwards', masked.maskedAfter === false, 'captureMasked ' + masked.maskedAfter)

// 2. Control: with the exclusion off the same capture must contain the pill, otherwise
//    the gate is measuring the pill being missing rather than the mask working.
const off = await run('control exclusion off', { DSH_CU_OVERLAY_CAPTURE_EXCLUSION: 'off' })
if (off !== undefined) {
  gate('control: with exclusion off the pill IS in the captured frame',
    off.afterFrame - off.beforeFrame >= Math.max(3000, off.beforeFrame * 1.5),
    'frame accent ' + off.beforeFrame + ' -> ' + off.afterFrame)
}

console.log('pill-capture-mask: ' + (failures === 0 ? 'all gates pass' : failures + ' gate(s) failed'))
process.exit(failures === 0 ? 0 : 1)
