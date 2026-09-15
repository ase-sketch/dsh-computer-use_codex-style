# End-to-end live verification for the overlay, capture and interrupt behaviour.
# Every gate prints PASS or FAIL; nothing here needs a human hand.
#
# Escape and human input are driven by *untagged* injected input from another process.
# After the dwExtraInfo fix that is indistinguishable from a physical event to the
# helper's low-level hooks (and it is literally how a remote desktop delivers the
# operator's own clicks), so these gates cover the real paths without an operator.
# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = 'Continue'
$NL = [string][char]10
$root = $RepoRoot
$parity = Join-Path $root 'parity'
function Gate([string]$name, [bool]$ok, [string]$detail) {
  $tag = 'FAIL'
  if ($ok) { $tag = 'PASS' }
  Write-Output ('[{0}] {1} :: {2}' -f $tag, $name, $detail)
}
function AccentCount([string]$text) {
  $m = [regex]::Match($text, 'pill pixels: (\d+)')
  if ($m.Success) { return [int]$m.Groups[1].Value }
  return -1
}
Get-Process dsh-computer-use -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400
# Always restart it: a long-lived instance drifts into a geometry the app re-applies on
# its own (measured 960x1470 at y=0, which cannot fit on screen), and every coordinate
# test needs the window fully visible.
Get-Process ParityTarget -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 700
Start-Process (Join-Path $parity 'ParityTarget.exe')
Start-Sleep -Seconds 3
# All of these tests record coordinates against the canonical geometry, and the
# interactive harness may have moved or enlarged the window, so reset it first.
$geometry = & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $parity 'raise-target.ps1') 2>&1 | Out-String
Write-Output ('  ' + $geometry.Trim())
Gate 'setup: parity target fully on screen' ($geometry -match 'fullyOnScreen=True') $geometry.Trim()
Start-Sleep -Milliseconds 400

# --- 1. cursor: motion, foreground storm, landing ---------------------------
$trace = & node (Join-Path $parity 'cursor-trace.mjs') 2>&1 | Out-String
$traceLines = $trace -split $NL
Gate 'cursor: click accepted' ($trace -match 'second click -> ok') 'second click ok'
$fgLine = ($traceLines | Select-String 'foregrounds:').Line
Gate 'cursor: no self-inflicted foreground storm' ($fgLine -notmatch 'DshComputerUse') $fgLine
# Was `tick=20/20`: that asserted the *implementation* (20 frames x 16 ms) and so
# certified defect VIS-08 (every move lasting ~0.32 s). The honest duration claim now
# lives in parity/check-claims.ps1 (C7, duration must scale with distance); here we
# only assert that the move finished and the sprite is parked.
Gate 'cursor: animation completes' ($trace -match 'active=false') (($traceLines | Select-String 'after second click \+400ms').Line)

# --- 2. cursor pixels in the model-facing screenshot ------------------------
$cursorScan = & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $parity 'lag-scan.ps1') 2>&1 | Out-String
$lagA = [regex]::Match($cursorScan, 'lag-a\.jpg dark n=(\d+) bbox=\((\d+),(\d+)\)-\((\d+),(\d+)\)')
Gate 'cursor: glyph pixels present in the capture' ($lagA.Success -and [int]$lagA.Groups[1].Value -gt 1000) $lagA.Value
Gate 'cursor: glyph in the lower-left (second click)' ($lagA.Success -and [int]$lagA.Groups[4].Value -gt 250) $lagA.Value

# --- 3. content freshness ---------------------------------------------------
$fresh = & node (Join-Path $parity 'fresh-test.mjs') 2>&1 | Out-String
$diff = & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $parity 'fresh-diff.ps1') 2>&1 | Out-String
$after = [int]([regex]::Match($diff, 'textbox fresh-0 -> fresh-1 differing pixels: (\d+)').Groups[1].Value)
$stable = [int]([regex]::Match($diff, 'textbox fresh-1 -> fresh-2 differing pixels: (\d+)').Groups[1].Value)
Gate 'capture: post-action frame shows the action' ($after -gt 1000) ('fresh-0 -> fresh-1 = ' + $after + ' px')
Gate 'capture: settled frame is stable' ($stable -eq 0) ('fresh-1 -> fresh-2 = ' + $stable + ' px')

# --- 4. status pill --------------------------------------------------------
$env:DSH_CU_OVERLAY_CAPTURABLE = '1'
$pill = & node (Join-Path $parity 'pill-probe.mjs') 2>&1 | Out-String
$px = & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $parity 'pill-crop.ps1') 2>&1 | Out-String
Gate 'pill: composition display attached' ($pill -match 'displayComposition=true') (($pill -split $NL | Select-String 'overlay visible=').Line)
Gate 'pill: accent body drawn (DirectComposition)' ((AccentCount $px) -gt 500) (($px -split $NL | Select-String 'pill pixels').Line)
$env:DSH_CU_ULW_OVERLAY = '1'
$pill2 = & node (Join-Path $parity 'pill-probe.mjs') 2>&1 | Out-String
$px2 = & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $parity 'pill-crop.ps1') 2>&1 | Out-String
Remove-Item Env:\DSH_CU_ULW_OVERLAY
Remove-Item Env:\DSH_CU_OVERLAY_CAPTURABLE
Gate 'pill: fallback path selected' ($pill2 -match 'displayComposition=false') (($pill2 -split $NL | Select-String 'overlay visible=').Line)
Gate 'pill: accent body drawn (layered fallback)' ((AccentCount $px2) -gt 500) (($px2 -split $NL | Select-String 'pill pixels').Line)

# --- 5. window states: observe / activate_window / retry --------------------
Get-Process dsh-computer-use -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400
$states = & node (Join-Path $parity 'window-states.mjs') 2>&1 | Out-String
foreach ($line in ($states -split $NL)) {
  $m = [regex]::Match($line, '\[(PASS|FAIL)\] (.+)$')
  if ($m.Success) {
    Gate ('window-state: ' + $m.Groups[2].Value.Trim()) ($m.Groups[1].Value -eq 'PASS') (($states -split $NL | Select-String -Pattern 'observe:' -Context 0,0 | Select-Object -First 1).Line)
  }
}
$stateGates = ([regex]::Matches($states, '\[(PASS|FAIL)\]')).Count
Gate 'window-state: all cases ran' ($stateGates -ge 5) ($stateGates.ToString() + ' cases')

# --- 6. cursor motion: the official landing contract ------------------------
# Re-raise the target first: the occlusion case deliberately left another window on top,
# and a coordinate click would otherwise land on that window instead of the target.
& pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $parity 'raise-target.ps1') | Out-Null
Get-Process dsh-computer-use -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400
$motion = & node (Join-Path $parity 'motion-curve.mjs') 2>&1 | Out-String
# Only `[PASS]` lines count. An `INVALID ... landedErr=998.6px` line reports a *rejected*
# measurement (target lost / click refused), and matching its number made one invalid run look
# like a 998 px landing error. Invalid runs are a separate gate instead of a silent number.
$errors = [regex]::Matches($motion, '(?m)^\[PASS\][^\r\n]*landedErr=([0-9.]+)px')
$ratios = [regex]::Matches($motion, '(?m)^\[PASS\][^\r\n]*ratio=([0-9.]+)')
$invalid = ([regex]::Matches($motion, '(?m)^INVALID')).Count
$worst = 0.0
foreach ($x in $errors) { $v = [double]$x.Groups[1].Value; if ($v -gt $worst) { $worst = $v } }
$maxRatio = 0.0
foreach ($x in $ratios) { $v = [double]$x.Groups[1].Value; if ($v -gt $maxRatio) { $maxRatio = $v } }
Gate 'motion: every move lands exactly on target' ($errors.Count -ge 3 -and $worst -le 1.5) ('worst landing error ' + $worst + ' px over ' + $errors.Count + ' moves')
Gate 'motion: two-segment moves bow off the straight line' ($maxRatio -gt 0.02) ('max bulge ratio ' + $maxRatio)
Gate 'motion: no invalid measurement was accepted as evidence' ($invalid -eq 0) ($invalid.ToString() + ' INVALID case(s)')

# --- 7. plugin transport: Escape interrupt, human input, approval -----------
& pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $parity 'raise-target.ps1') | Out-Null
Get-Process dsh-computer-use -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400
$flow = & node (Join-Path $parity 'interactive-physical.mjs') --esc=inject --human=inject 2>&1 | Out-String
$flowGates = 0
foreach ($line in ($flow -split $NL)) {
  $m = [regex]::Match($line, '\[(PASS|FAIL)\] (.+?) :: (.*)$')
  if ($m.Success) {
    $flowGates++
    Gate ('plugin: ' + $m.Groups[2].Value.Trim()) ($m.Groups[1].Value -eq 'PASS') $m.Groups[3].Value.Trim()
  }
}
Gate 'plugin: all transport gates ran' ($flowGates -ge 10) ($flowGates.ToString() + ' gates reported')

# --- 8. overlay lifetime + system-pointer suppression ------------------------
# The two operator-visible states this family exists for: a synthetic cursor with the
# real pointer still drawn next to it (the reported "two cursors"), and a synthetic
# cursor that outlives its turn.
& pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $parity 'raise-target.ps1') | Out-Null
Get-Process dsh-computer-use -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400
$life = & node (Join-Path $parity 'overlay-lifecycle.mjs') 2>&1 | Out-String
$lifeGates = 0
foreach ($line in ($life -split $NL)) {
  $m = [regex]::Match($line, '^(PASS|FAIL) (.+?)(?:  (\{.*\}))?$')
  if ($m.Success) {
    $lifeGates++
    Gate ('overlay: ' + $m.Groups[2].Value.Trim()) ($m.Groups[1].Value -eq 'PASS') $m.Groups[3].Value.Trim()
  }
}
Gate 'overlay: all lifecycle gates ran' ($lifeGates -ge 16) ($lifeGates.ToString() + ' gates reported')

# --- 9. plugin lifecycle wiring (source contract) ---------------------------
# Scope-filtered dispatch reaches a listener only on an equal or enclosing scope, so the
# turn-end release must be registered by the host-plane service. A preset-plane listener
# compiles, reads correctly, and never fires -- which is exactly how the overlay survived
# the end of the task.
$hostSrc = Get-Content (Join-Path $root 'src\index.js') -Raw
$toolSrc = Get-Content (Join-Path $root 'src\tool.js') -Raw
$hostHook = ($hostSrc -match "on\('session/event'") -and ($hostSrc -match 'turn/end') -and ($hostSrc -match 'releaseOverlay\(\)')
$presetHook = $toolSrc -match "on\('session/event'"
Gate 'plugin: turn-end release registered on the host-plane service' $hostHook 'index.js ctx.on(session/event) -> releaseOverlay()'
Gate 'plugin: no preset-plane session listener' (-not $presetHook) 'tool.js does not register ctx.on(session/event)'
# --- 10. plugin lifecycle wiring (real Cordis dispatch) ---------------------
# Mounts the real service against the real SessionStore and appends the real `turn/end`
# event, so this covers the wiring itself rather than the source text. The plugin's peer
# dependencies resolve through the harness checkout's tsx loader, exactly as the host
# resolves them at runtime.
# Point DSH_HARNESS at the harness checkout; the sibling directory and ~/deepseek-harness
# are tried next (tsx resolves the plugin's peer dependencies from there).
$checkout = $env:DSH_HARNESS
if (-not $checkout) {
  foreach ($candidate in @((Join-Path (Split-Path -Parent $RepoRoot) 'deepseek-harness'), (Join-Path $env:USERPROFILE 'deepseek-harness'))) {
    if (Test-Path (Join-Path $candidate 'node_modules\tsx')) { $checkout = $candidate; break }
  }
}
if (-not $checkout) { $checkout = Join-Path (Split-Path -Parent $RepoRoot) 'deepseek-harness' }
if (Test-Path (Join-Path $checkout 'node_modules\tsx')) {
  Push-Location $checkout
  $pluginLife = & node --import tsx/esm (Join-Path $parity 'plugin-lifecycle.mjs') 2>&1 | Out-String
  Pop-Location
  foreach ($line in ($pluginLife -split $NL)) {
    $m = [regex]::Match($line, '^(PASS|FAIL) (.+?)(?:  (.*))?$')
    if ($m.Success) {
      Gate ('plugin-lifecycle: ' + $m.Groups[2].Value.Trim()) ($m.Groups[1].Value -eq 'PASS') $m.Groups[3].Value.Trim()
    }
  }
  $lifePluginGates = ([regex]::Matches($pluginLife, '(?m)^(PASS|FAIL) ')).Count
  Gate 'plugin-lifecycle: all wiring gates ran' ($lifePluginGates -ge 10) ($lifePluginGates.ToString() + ' gates reported')
} else {
  Gate 'plugin-lifecycle: harness checkout with tsx present' $false ('missing ' + (Join-Path $checkout 'node_modules\tsx'))
}
# --- 11. accessibility: official-vs-ours rich-window A/B --------------------
# The older golden gate could only compare ParityTarget, whose tree carries no element state
# at all, so AX-19..AX-23 (field order `role (state) name`, verbatim control-type casing such
# as `SplitButton`, non-root `selectable` / non-root `Secondary Actions`, whitespace-normalised
# names, and the 250-node walk budget) were structurally invisible to it. This drives the
# OFFICIAL helper and ours against the same rich window in the same session and compares the
# tree body byte for byte.
#
# The official helper is launched with a THROWAWAY CODEX_HOME: its notify rewrite doubles
# backslashes on every run and once inflated the real ~/.codex/config.toml to 2.1 GB.
# Discover the official helper instead of hardcoding a per-machine runtime hash.
$codexRuntime = Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\runtimes\cua_node'
$officialHelper = Get-ChildItem $codexRuntime -Recurse -Filter 'codex-computer-use.exe' -ErrorAction SilentlyContinue |
  Select-Object -First 1 -ExpandProperty FullName
Gate 'ax-rich: official helper present for the A/B' (Test-Path $officialHelper) 'codex-computer-use.exe under the Codex runtime'
$axRich = & node (Join-Path $parity 'ax-rich-parity.mjs') --target auto 2>&1 | Out-String
if ($axRich -match 'AX-RICH GATE: PASS') {
  $which = [regex]::Match($axRich, 'target=(\w+)').Groups[1].Value
  $lines = [regex]::Match($axRich, 'PASS \((\d+) official lines').Groups[1].Value
  $residuals = [regex]::Match($axRich, '(\d+) documented residual').Groups[1].Value
  Gate 'ax-rich: tree body byte-identical to the official' $true ($which + ', ' + $lines + ' official lines, ' + $residuals + ' documented residual(s)')
  Gate 'ax-rich: tail sections identical' ($axRich -match 'tail-sections-identical=true') 'focused sentence / Selected / Document text presence'
  Gate 'ax-rich: accessibility key set identical' ($axRich -match 'keys-identical=true') 'tree + focused_element + document_text'
} elseif ($axRich -match 'cannot compare') {
  # A loud skip: no rich window is open on this desktop, so there is nothing to compare.
  # The official-helper-present gate above still runs, so a missing binary cannot hide here.
  Write-Output ('[SKIP] ax-rich: no Word/Explorer target open :: ' + (($axRich -split $NL | Select-String 'cannot compare').Line))
} else {
  $why = (($axRich -split $NL | Select-String '^  - ') | Select-Object -First 4) -join '; '
  Gate 'ax-rich: tree body byte-identical to the official' $false $why
}
# The focused-sentence contract only exists while the target window actually holds focus, so
# the rich-window comparison above cannot see it (Word's tail has the document text instead).
# verify-all starts ParityTarget, so this second A/B covers the foreground case end to end:
# both sides must name the same element as focused.
$axParity = & node (Join-Path $parity 'ax-rich-parity.mjs') --target parity --focus 2>&1 | Out-String
if ($axParity -match 'AX-RICH GATE: PASS') {
  Gate 'ax-parity: tree body byte-identical to the official' $true 'ParityTarget, official helper driven live'
  $focusLine = [regex]::Match($axParity, 'focused-sentence-identical=(\w+) official="?([^"' + [char]10 + ']*)').Groups
  Gate 'ax-parity: focused sentence identical' ($axParity -match 'focused-sentence-identical=true') ($focusLine[2].Value.Trim())
} else {
  $whyParity = (($axParity -split $NL | Select-String '^  - ') | Select-Object -First 4) -join '; '
  Gate 'ax-parity: tree body byte-identical to the official' $false $whyParity
}

# Interrupt-marker lifecycle (live helper, no desktop). The marker is per-turn state: the
# transport refuses later calls in that turn after the user presses Escape. DSH used to only
# ever write it, so one Escape refused the scope forever -- three Wave-3 agents independently
# hit an hours-old 0-byte `interrupts/dsh/turn` that made every default-scope request answer
# with the physical-Escape message, and `end_turn` itself was refused by that same marker.
$markerGate = & node (Join-Path $parity 'interrupt-marker.mjs') 2>&1 | Out-String
foreach ($line in ($markerGate -split $NL)) {
  if ($line -match '^(PASS|FAIL) (interrupt: .+?)  (.*)$') {
    Gate ('marker: ' + $matches[2]) ($matches[1] -eq 'PASS') $matches[3]
  }
}
$markerGates = ([regex]::Matches($markerGate, '(?m)^(PASS|FAIL) interrupt: ')).Count
Gate 'marker: all lifecycle gates reported' ($markerGates -ge 5) ($markerGates.ToString() + ' gates reported')

# --- 12. sidecar-level observe -> act (the real plugin path) ----------------
# This is V3's deeper form. Every other gate in this file drives the helper DIRECTLY, so the
# plugin's own turn bookkeeping was invisible to all of them. The first real end-to-end task
# (2026-09-14) failed with `coordinate input target is unavailable` on every input after a
# successful `get_window_state`, because tool.js stamped a NEW turn id (the call id) per tool
# call and the sidecar sends `end_turn` whenever the turn scope changes -- which flushes the
# helper's observation lease. This gate goes through the real `Sidecar` and the real turn-meta
# builder, and it is the only gate that could have caught it.
if (Test-Path (Join-Path $checkout 'node_modules\tsx')) {
  Push-Location $checkout
  $observeAct = & node --import tsx/esm (Join-Path $parity 'sidecar-observe-act.mjs') 2>&1 | Out-String
  Pop-Location
  foreach ($line in ($observeAct -split $NL)) {
    $m = [regex]::Match($line, '^(PASS|FAIL) (.+?)  (.*)$')
    if ($m.Success) { Gate ('sidecar: ' + $m.Groups[2].Value.Trim()) ($m.Groups[1].Value -eq 'PASS') $m.Groups[3].Value.Trim() }
  }
  $observeGates = ([regex]::Matches($observeAct, '(?m)^(PASS|FAIL) ')).Count
  Gate 'sidecar: observe->act gates reported' ($observeGates -ge 7) ($observeGates.ToString() + ' gates reported')
} else {
  Gate 'sidecar: harness checkout with tsx present' $false ('missing ' + (Join-Path $checkout 'node_modules\tsx'))
}

# The Python fake backend must never reach the real desktop. `backend: fake` used to start the
# native helper whenever the built exe existed, so a fake run observed and drove the real
# machine (and only machines WITHOUT a build saw the intended fake surface). `src/smoke.mjs`
# is the canary: it asserts the fake response shape that only the Python engine produces.
$smoke = & node (Join-Path $root 'src\smoke.mjs') 2>&1 | Out-String
Gate 'fake-backend: the Python fake engine serves the call' ($smoke -match '"backend":"fake"') (($smoke -split $NL | Where-Object { $_ -match 'ok' } | Select-Object -First 1))
$smokeImages = [regex]::Match($smoke, '"images":(\d+)').Groups[1].Value
Gate 'fake-backend: a screenshot image is returned' ($smokeImages -ne '' -and [int]$smokeImages -ge 1) ('images=' + $smokeImages)

Get-Process dsh-computer-use -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output 'verification finished'