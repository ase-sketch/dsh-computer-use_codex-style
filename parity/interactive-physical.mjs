// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// Interactive physical-action acceptance: physical Escape, real human input, and the
// launch_app approval contract. Phases run in order and print READY markers.
//
// Robustness notes learned from the live runs:
//  * while a helper is dying from Escape it can still answer one queued request with the
//    official Escape error, so a poll must treat that as "interrupted", not as fatal;
//  * the exit code arrives on the 'exit' event, which can land after the pending request
//    is rejected, so the gate waits for it.
import { execSync } from 'node:child_process'

/// Raise the target so the operator can see it; another process may change z-order
/// without activation rights.
function raiseTarget() {
  try {
    // An operator has to be able to find the window by eye, so operator mode enlarges
    // it; the automated modes keep the canonical geometry every test records against.
    const geometry = HUMAN === 'operator' ? ' -X 40 -Y 40 -W 1360 -H 880' : ''
    return execSync(
      'pwsh -NoProfile -ExecutionPolicy Bypass -File repoRoot + "/parity/raise-target.ps1"' + geometry,
      { encoding: 'utf8' },
    ).trim()
  } catch (error) {
    return 'raise failed: ' + String(error.message).slice(0, 80)
  }
}
import fs from 'node:fs'
import path from 'node:path'
import {
  Sidecar,
  USER_INTERRUPT_MESSAGE,
  turnScopeOf,
  interruptMarkerPath,
} from '../src/sidecar.js'

const ROOT = repoRoot + ''
const LOG = path.join(ROOT, 'parity', 'interactive.log')
const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').slice(7)
/// How the "human" input is produced: `operator` waits for a physical click, `inject`
/// sends an untagged click from another process. Untagged is exactly how a remote
/// desktop delivers the operator's own clicks, so both exercise the same code path.
const HUMAN = (process.argv.find((a) => a.startsWith('--human=')) || '').slice(8) || 'operator'
/// Same idea for the Escape interrupt: `inject` sends an untagged Escape from another
/// process, which the helper now classifies exactly like a physical key.
const ESC = (process.argv.find((a) => a.startsWith('--esc=')) || '').slice(6) || 'operator'
const runPhase = (n) => !ONLY || ONLY === n
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const short = (text) => String(text || '').slice(0, 70)
const isInterrupt = (error) =>
  Boolean(error) &&
  (error.message === USER_INTERRUPT_MESSAGE ||
    String(error.message || '').includes('stopped by the user with the physical Escape key'))

const lines = []
function say(text) {
  const stamp = new Date().toISOString().slice(11, 19)
  const line = '[' + stamp + '] ' + text
  lines.push(line)
  fs.writeFileSync(LOG, lines.join('\n') + '\n')
  console.log(line)
}
function gate(name, ok, detail) {
  say((ok ? '[PASS] ' : '[FAIL] ') + name + ' :: ' + detail)
}
const sidecar = new Sidecar({
  engineRoot: ROOT,
  timeoutMs: 10000,
  launchAppTimeoutMs: 15000,
  preserveHelperOnTimeout: false,
})
let lastExit = null

const call = (meta, name, args) =>
  sidecar.request('call', { name, arguments: args || {}, meta: meta || {} })

await sidecar.start()
const listed = await call({}, 'list_windows')
const windows = Array.isArray(listed?.value) ? listed.value : listed?.value?.windows || []
const target = windows.find((w) => w.title === 'Parity Target')
if (!target) {
  say('TARGET_MISSING: run parity/ParityTarget.exe first')
  process.exit(1)
}
const win = { app: target.app, id: target.id }
const approved = (meta) => ({ ...meta, 'x-oai-cua-approved-app': target.app })
say('target window: ' + target.app + ' #' + target.id)

function watchExit() {
  sidecar.primary.child?.on('exit', (code, signal) => {
    lastExit = { code, signal }
    say('helper exited: code=' + code + ' signal=' + (signal || 'none'))
  })
}
watchExit()

let viewport = { x: 40, y: 40 }
async function observe(meta) {
  const shot = await call(approved(meta), 'get_window_state', {
    window: win,
    include_screenshot: true,
    include_text: false,
  })
  const first = shot?.value?.screenshots?.[0] || null
  if (first && Number.isFinite(first.originX)) viewport = { x: first.originX, y: first.originY }
  return first?.id || null
}
async function armOverlay(meta) {
  const sid = await observe(meta)
  await call(approved(meta), 'click', { window: win, screenshotId: sid, x: 300, y: 300 })
  return sid
}
async function generation() {
  const diag = await sidecar.request('diagnostic_state', {})
  return diag?.inputMonitor?.generation ?? -1
}

// ---------------------------------------------------------------- phase 1: Esc
if (runPhase('phase1')) {
  say('=== phase 1: physical Escape ===')
  const meta1 = { conversationId: 'dsh-interactive', turnId: 'turn-esc-' + Date.now() }
  const sid1 = await armOverlay(meta1)
  say('overlay up, Escape hook armed (screenshot ' + sid1 + ')')
  if (ESC === 'inject') {
    say('injecting an untagged, human-equivalent Escape')
    try {
      say(
        '  ' +
          execSync('pwsh -NoProfile -ExecutionPolicy Bypass -File repoRoot + "/parity/inject-key.ps1"', {
            encoding: 'utf8',
          }).trim(),
      )
    } catch (error) {
      say('  injection failed: ' + short(error.message))
    }
  } else {
    say('READY-1 >>> press the PHYSICAL Escape key now (waiting up to 6 minutes)')
  }
  let interruptError = null
  const deadline1 = Date.now() + 360000
  while (Date.now() < deadline1) {
    try {
      await call(approved(meta1), 'list_windows')
    } catch (error) {
      interruptError = error
      break
    }
    await sleep(900)
  }
  if (!interruptError) {
    gate('esc: interrupt observed', false, 'nothing within 6 minutes')
  } else {
    gate('esc: the stop is reported with an official sentence', isInterrupt(interruptError), JSON.stringify(interruptError.message))
    await sleep(900)
    watchExit()
    gate('esc: helper exit status 130', lastExit?.code === 130, JSON.stringify(lastExit))
    const marker = interruptMarkerPath(turnScopeOf(meta1))
    gate('esc: official interrupt marker written', Boolean(marker) && fs.existsSync(marker), String(marker))
    await sleep(1200)
    let refusal = null
    try {
      await call(approved(meta1), 'list_windows')
    } catch (error) {
      refusal = error
    }
    gate('esc: every later call in that turn is refused', isInterrupt(refusal), JSON.stringify(short(refusal?.message) || 'call succeeded'))
    const metaNew = { conversationId: 'dsh-interactive', turnId: 'turn-after-esc-' + Date.now() }
    let recovered = null
    try {
      recovered = await call(approved(metaNew), 'list_windows')
    } catch (error) {
      recovered = { error: error.message }
    }
    gate(
      'esc: a new turn works again',
      Array.isArray(recovered?.value) || Array.isArray(recovered?.value?.windows),
      JSON.stringify(short(recovered?.error) || 'windows returned'),
    )
  }
}

// ------------------------------------------------------- phase 2: human input
if (runPhase('phase2')) {
  try {
  say('=== phase 2: real human input ===')
  let done = false
  for (let attempt = 1; attempt <= 4 && !done; attempt++) {
    const meta2 = { conversationId: 'dsh-interactive', turnId: 'turn-human-' + Date.now() + '-' + attempt }
    let sid2 = null
    // Restore + raise the target *before* observing: a minimized window cannot be
    // observed at all (official error: `window is minimized; call activate_window...`).
    say('  ' + raiseTarget())
    try {
      sid2 = await armOverlay(meta2)
    } catch (error) {
      say('attempt ' + attempt + ': arming failed (' + short(error.message) + '), retrying')
      try {
        await call(approved(meta2), 'activate_window', { window: win, id: win.id, app: win.app })
        sid2 = await armOverlay(meta2)
      } catch (second) {
        say('attempt ' + attempt + ': activate_window did not help (' + short(second.message) + ')')
        await sleep(1500)
        continue
      }
    }
    // Re-observe after moving/resizing so the recorded geometry is the one the operator
    // will actually click, otherwise the action is refused with the official
    // 'window bounds changed before coordinate input'.
    sid2 = await armOverlay(meta2)
    const before = await generation()
    const diag0 = await sidecar.request('diagnostic_state', {})
    const fg = diag0?.foreground || {}
    say(
      'attempt ' + attempt + ': armed with fresh bounds; generation=' + before +
        ' monitorAvailable=' + (diag0?.inputMonitor?.available) +
        ' foreground=' + JSON.stringify(fg.exe || '') + '#' + (fg.inputHwnd || 0),
    )
    if (attempt === 1) {
      say('   >>> the Parity Target window now covers the upper-left of the screen (about 1360x880 at 40,40)')
    }
    if (HUMAN === 'inject') {
      say('injecting an untagged human-equivalent click inside the target window')
      try {
        const point = { x: viewport.x + 300, y: viewport.y + 300 }
        const out = execSync(
          'pwsh -NoProfile -ExecutionPolicy Bypass -File repoRoot + "/parity/inject-click.ps1" ' +
            point.x + ' ' + point.y,
          { encoding: 'utf8' },
        )
        say('  ' + out.trim())
      } catch (error) {
        say('  injection failed: ' + short(error.message))
      }
    } else {
      say('READY-2 >>> click inside that window now (waiting up to 6 minutes)')
    }
    let humanError = null
    let interrupted = false
    let missed = false
    let lastBeat = Date.now()
    const deadline2 = Date.now() + 300000
    while (Date.now() < deadline2) {
      let diag = null
      try {
        diag = await sidecar.request('diagnostic_state', {})
      } catch (error) {
        say('attempt ' + attempt + ': poll interrupted (' + short(error.message) + '), re-arming')
        interrupted = true
        break
      }
      const gen = diag?.inputMonitor?.generation ?? -1
      if (gen === before && Date.now() - lastBeat > 6000) {
        lastBeat = Date.now()
        const im = diag?.inputMonitor || {}
        say(
          '  waiting... generation=' + gen + ' dirty=' + im.dirty +
            ' armed=' + im.armed + ' installed=' + im.installed + ' synthetic=' + im.synthetic +
            ' hooks[mouse=' + im.mouseEvents + ' downs=' + im.mouseDowns + ' injected=' + im.mouseDownsInjected + ' keys=' + im.keyEvents + ']' +
            ' reason=' + JSON.stringify(im.reason || '') +
            ' fg=' + JSON.stringify(diag?.foreground?.exe || ''),
        )
      }
      if (gen !== before) {
        const dirty = diag?.inputMonitor?.dirty
        const reason = diag?.inputMonitor?.reason
        const fg2 = diag?.foreground || {}
        say(
          'human input observed: generation ' + before + ' -> ' + gen +
            ' targetDirty=' + dirty + ' reason=' + JSON.stringify(reason) +
            ' foreground=' + JSON.stringify(fg2.exe || '') + '#' + (fg2.inputHwnd || 0) +
            ' monitorAvailable=' + (diag?.inputMonitor?.available),
        )
        if (dirty !== true) {
          say('the click did not register on the target window; asking for another click')
          missed = true
          break
        }
        try {
          await call(approved(meta2), 'click', { window: win, screenshotId: sid2, x: 300, y: 300 })
        } catch (error) {
          humanError = error
        }
        break
      }
      await sleep(600)
    }
    if (interrupted || missed) {
      await sleep(1500)
      continue
    }
    gate(
      'human input: the next action is refused with the official sentence',
      typeof humanError?.message === 'string' && humanError.message.includes('user input was detected'),
      JSON.stringify(humanError?.message || 'action succeeded (no refusal)'),
    )
    if (humanError) {
      // The window may have lost the foreground to the human's click, and Windows can
      // refuse the implicit re-activation; the official `activate_window` tool is the
      // documented way out, so use it and prove that path too.
      let sid3 = null
      try {
        sid3 = await observe(meta2)
      } catch (error) {
        say('observation failed (' + short(error.message) + '); calling activate_window first')
        try {
          await call(approved(meta2), 'activate_window', { window: win, id: win.id, app: win.app })
        } catch (activateError) {
          say('activate_window failed: ' + short(activateError.message))
        }
        sid3 = await observe(meta2)
      }
      let after = null
      try {
        after = await call(approved(meta2), 'click', { window: win, screenshotId: sid3, x: 300, y: 300 })
      } catch (error) {
        after = { error: error.message }
      }
      gate('human input: a fresh observation unblocks the next action', after?.ok === true, JSON.stringify(short(after?.error) || 'ok'))
    }
    done = true
  }
  } catch (error) {
    say('phase 2 aborted: ' + short(error.message))
  }
}

// ------------------------------------------------------------ phase 3: approval
if (runPhase('phase3')) {
  say('=== phase 3: launch_app approval contract ===')
  const meta3 = { conversationId: 'dsh-interactive', turnId: 'turn-approval-' + Date.now() }
  const ask = await call(meta3, 'launch_app', { app: 'notepad.exe' })
  const payload = ask?.approvalRequest || null
  gate('approval: helper asks before launching an unapproved app', Boolean(payload), JSON.stringify(payload))
  gate(
    'approval: request carries the four official fields',
    Boolean(payload && payload.app && payload.displayName && payload.riskLevel && payload.allowPersistentApproval === true),
    JSON.stringify(payload),
  )
  say('message the model sees on the ask: ' + JSON.stringify(ask?.error))
  const ok = await call({ ...meta3, 'x-oai-cua-approved-app': 'notepad.exe' }, 'launch_app', { app: 'notepad.exe' })
  gate('approval: the approved retry proceeds', ok?.ok === true, JSON.stringify(short(ok?.error) || 'launched'))
  try { execSync('taskkill /IM notepad.exe /F', { stdio: 'ignore' }) } catch {}
}

say('=== interactive run finished (see parity/interactive.log) ===')
process.exit(0)
