# Honest claim audit: the checks that were missing, wrong, or tautological.
#
# `verify-all.ps1` drives the desktop and asserts behaviour. It had (and still has) three
# blind spots, all found in the 2026-09-14 deep dive (analysis/deep-dive/10-GAP-REGISTER.md
# section 1): it never touches the plugin transport, it never touches the AX tree, and one
# of its gates certified a defect as expected behaviour. This script adds the static and
# wire-level claims that verify-all cannot see.
#
# It is EXPECTED TO BE RED until the corresponding fixes land; every red line is a tracked
# work item, not a flake. Run:  pwsh -File parity/check-claims.ps1
# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = 'Continue'
$root = $RepoRoot
$parity = Join-Path $root 'parity'
# The harness checkout is where tsx resolves the plugin's peer dependencies. Point
# DSH_HARNESS at it; otherwise the sibling directory and ~/deepseek-harness are tried.
$checkout = $env:DSH_HARNESS
if (-not $checkout) {
  foreach ($candidate in @((Join-Path (Split-Path -Parent $RepoRoot) 'deepseek-harness'), (Join-Path $env:USERPROFILE 'deepseek-harness'))) {
    if (Test-Path (Join-Path $candidate 'node_modules\tsx')) { $checkout = $candidate; break }
  }
}
if (-not $checkout) { $checkout = Join-Path (Split-Path -Parent $RepoRoot) 'deepseek-harness' }
$official = ($CodexHome + '\plugins\cache\openai-bundled\computer-use\26.903.61454')
$results = New-Object System.Collections.ArrayList
function Claim([string]$id, [string]$title, [bool]$ok, [string]$evidence) {
  $tag = if ($ok) { 'PASS' } else { 'RED ' }
  [void]$results.Add([pscustomobject]@{ id = $id; ok = $ok })
  Write-Output ('[{0}] {1} {2} :: {3}' -f $tag, $id, $title, $evidence)
}
$tsxOk = Test-Path (Join-Path $checkout 'node_modules\tsx')

# C1 -- the always-on prompt is measured on the plane the model actually reads.
$budget = 'n/a'
if ($tsxOk) {
  Push-Location $checkout
  $budget = & node --import tsx/esm (Join-Path $parity 'claim-prompt-budget.mjs') 2>&1 | Out-String
  Pop-Location
  $budgetJson = $null
  try { $budgetJson = ($budget -split "`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1) | ConvertFrom-Json } catch {}
  if ($budgetJson) {
    Claim 'C1' 'always-on prompt within budget (real JS plane)' $budgetJson.ok ('alwaysOn=' + $budgetJson.alwaysOnChars + ' budget=' + $budgetJson.budget + ' official=' + $budgetJson.officialAlwaysOn + ' ratio=' + $budgetJson.ratio)
  } else { Claim 'C1' 'always-on prompt within budget (real JS plane)' $false $budget.Trim() }
} else { Claim 'C1' 'always-on prompt within budget (real JS plane)' $false 'tsx unavailable' }

# C2 -- the shipped reference documents are byte-identical to the official plugin copies.
$pairs = @{ 'guidance.md' = 'B171B26BC19F4922'; 'api.md' = 'C36D005FB98ED798'; 'confirmations.md' = '9C45B3EB20E4A7FB' }
$identical = 0
$mismatch = @()
foreach ($name in $pairs.Keys) {
  $ours = Join-Path $root ('helper-rs\assets\prompts\' + $name)
  $theirs = Join-Path $official ('docs\' + $name)
  if ((Test-Path $ours) -and (Test-Path $theirs)) {
    $a = (Get-FileHash -LiteralPath $ours -Algorithm SHA256).Hash
    $b = (Get-FileHash -LiteralPath $theirs -Algorithm SHA256).Hash
    if ($a -eq $b) { $identical++ } else { $mismatch += $name }
  } else { $mismatch += ($name + '(missing)') }
}
Claim 'C2' 'bundled official documents byte-identical' ($identical -eq 3) ('identical=' + $identical + '/3 mismatched=' + ($mismatch -join ','))

# C3 -- the wire envelope the sidecar writes is the official one.
$wireOut = 'n/a'
if ($tsxOk) {
  Push-Location $checkout
  $wireOut = & node --import tsx/esm (Join-Path $parity 'sidecar-wire.mjs') 2>&1 | Out-String
  Pop-Location
  $wireJson = $null
  try { $wireJson = ($wireOut -split "`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1) | ConvertFrom-Json } catch {}
  if ($wireJson) {
    Claim 'C3' 'sidecar writes the official request envelope' $wireJson.ok ('messages=' + $wireJson.messages + ' withJsonRpc=' + $wireJson.withJsonRpc + ' keys=' + ($wireJson.firstKeys -join '/'))
  } else { Claim 'C3' 'sidecar writes the official request envelope' $false $wireOut.Trim() }
} else { Claim 'C3' 'sidecar writes the official request envelope' $false 'tsx unavailable' }

# C4 -- the helper child does not inherit the whole parent environment.
$sidecarSrc = Get-Content (Join-Path $root 'src\sidecar.js') -Raw
$inherit = ([regex]::Matches($sidecarSrc, '\.\.\.process\.env')).Count
Claim 'C4' 'helper child gets a whitelisted environment' ($inherit -eq 0) ('. . .process.env occurrences=' + $inherit)

# C5 -- a helper that never becomes ready must not hang the session forever.
# The first version of this claim matched any `setTimeout`, and waitSpawn's `setTimeout(resolve, 40)`
# satisfied it -- a check passing for the wrong reason, which is the failure mode this whole file
# exists to prevent. The honest question is whether a helper that never becomes ready makes the
# wait REJECT.
$waitSpawn = [regex]::Match($sidecarSrc, 'async function waitSpawn[\s\S]{0,900}')
$hasTimeout = $waitSpawn.Success -and ($waitSpawn.Value -match 'setTimeout\([^)]{0,120}reject')
$c5ev = if ($waitSpawn.Success) { 'waitSpawn body checked' } else { 'waitSpawn not found' }
Claim 'C5' 'spawn wait has a startup timeout' $hasTimeout $c5ev

# C6 -- a missing prompt asset must be loud, not silently skipped.
$promptSrc = Get-Content (Join-Path $root 'src\prompt.js') -Raw
$silentSkip = ($promptSrc -match 'catch \(error\)') -and ($promptSrc -notmatch 'throw')
Claim 'C6' 'missing prompt asset fails loudly' (-not $silentSkip) ('silent skip: ' + $silentSkip)

# C7 -- move duration must sit inside the OFFICIAL's measured settle window.
#
# History: VIS-08 was "every move lasts ~0.32 s" (the sampler played a fixed 16 ms per frame),
# and the first criterion for this claim was a ratio derived from the decompiled polynomial.
# The M-C sampling round settled it with real measurements (deep-dive/11-official-sampling.md
# section 3, mirrored into official-constants.json -> cursorMotion.samples):
#   * the binary polynomial with blend=curve=0 is refuted (L=400 horizontal measures 691 ms
#     where it predicts 424 ms; L>=269 is 25-63% low),
#   * the tail is NOT monotonic (d760 786 ms > d998 651 ms) because duration also depends on
#     direction, so "strictly increasing" is the wrong criterion,
#   * the <=196 px single-segment band measures 304-373 ms, i.e. the fixed binary 0.24 s is
#     too fast; the model uses 0.34 s, the only value inside all three +/-40 ms windows.
# Each case therefore has to land inside ITS official window, and the long cases still have to
# be clearly longer than the short ones (that is what catches the fixed-320 ms regression).
$curve = Get-Content (Join-Path $parity 'motion-curve.json') -Raw | ConvertFrom-Json
$samples = (Get-Content (Join-Path $parity 'official-constants.json') -Raw | ConvertFrom-Json).cursorMotion.samples
$durations = @($curve | ForEach-Object { [int]$_.durationMs })
$compared = 0
$outside = @()
foreach ($case in $curve) {
  $reference = $samples | Where-Object { $_.label -eq $case.source } | Select-Object -First 1
  if (-not $reference) { $outside += ($case.label + ' -> no official sample for source ' + $case.source); continue }
  $compared++
  if (([int]$case.durationMs -lt [int]$reference.tSettleMinMs) -or ([int]$case.durationMs -gt [int]$reference.tSettleMaxMs)) {
    $outside += ($case.label + '(' + $case.source + ')= ' + $case.durationMs + 'ms outside [' + $reference.tSettleMinMs + ',' + $reference.tSettleMaxMs + ']')
  }
}
$short = ($curve | Where-Object { $_.label -eq 'short' }).durationMs
$long = ($curve | Where-Object { $_.label -eq 'long' }).durationMs
$small = ($curve | Where-Object { $_.label -eq 'small' }).durationMs
$ratio = if ($short) { [math]::Round($long / $short, 3) } else { 0 }
$smallRatio = if ($small) { [math]::Round($long / $small, 3) } else { $null }
$c7ok = ($compared -ge 3) -and ($outside.Count -eq 0) -and ($ratio -ge 1.2)
if ($null -ne $smallRatio) { $c7ok = $c7ok -and ($smallRatio -ge 1.5) }
$c7ev = 'durations=' + ($durations -join '/') + 'ms within-official-window=' + $compared + '/' + $curve.Count + ' long/short=' + $ratio
if ($null -ne $smallRatio) { $c7ev = $c7ev + ' long/small=' + $smallRatio + ' (<=196px band model 0.34s, official 0.304-0.373s)' } else { $c7ev = $c7ev + ' (no small case yet)' }
if ($outside.Count -gt 0) { $c7ev = $c7ev + ' OUTSIDE: ' + ($outside -join '; ') }
Claim 'C7' 'move duration sits inside the official measured window' $c7ok $c7ev

# C8 -- official constants have a single source of truth shared by both engines.
$constants = Join-Path $parity 'official-constants.json'
$c8ev = if (Test-Path $constants) { 'parity/official-constants.json' } else { 'missing: Rust and Python already drift (CW-10)' }
Claim 'C8' 'official constants have one source of truth' (Test-Path $constants) $c8ev

# C9 -- the official window identity survives the whole path: the predicate comes from the
# official function, and `resolve_window` matches with the identity-aware comparator
# (`app` is now `process:<full path>`, so a plain `eq_ignore_ascii_case` silently stops
# matching -- that regression was introduced and caught during the 2026-09-14 fixes).
$enumSrc = Get-Content (Join-Path $root 'helper-rs\src\enum_windows.rs') -Raw
$mainSrc = Get-Content (Join-Path $root 'helper-rs\src\main.rs') -Raw
$stateSrc = Get-Content (Join-Path $root 'helper-rs\src\state.rs') -Raw
$identityOk = ($enumSrc -match 'pub fn app_identity_matches')
$identityOk = $identityOk -and ($enumSrc -match 'official_window_predicate_truth_table')
$identityOk = $identityOk -and ($mainSrc -match 'app_identity_matches\(&w\.app, &app\)')
$identityOk = $identityOk -and ($stateSrc -match 'let process_name = crate::enum_windows::exe_name\(pid\)')
Claim 'C9' 'official window identity end to end' $identityOk 'predicate + resolve_window + process_name'

# C10 -- both engines agree with the official constants file (CW-10). The Rust side wires it
# through `include_str!` plus a compile-time assert; the Python path is checked here until it
# does the same.
$constantsJson = Get-Content (Join-Path $parity 'official-constants.json') -Raw | ConvertFrom-Json
$jpeg = [string]$constantsJson.capture.jpegQuality
$winrt = Get-Content (Join-Path $root 'computer_use\jpeg_winrt.py') -Raw
$wic = Get-Content (Join-Path $root 'computer_use\jpeg_wic.py') -Raw
$wgc = Get-Content (Join-Path $root 'computer_use\wgc_winrt.py') -Raw
$drift = @()
if ($winrt -notmatch [regex]::Escape($jpeg)) { $drift += ('jpeg_winrt.py != ' + $jpeg) }
if ($wic -notmatch '\b80\b') { $drift += 'jpeg_wic.py != 80' }
if ($wgc -notmatch 'SetIsCursorCaptureEnabled\(\s*True') { $drift += 'wgc_winrt.py cursor capture != True' }
Claim 'C10' 'Python engine matches the official constants' ($drift.Count -eq 0) (($drift -join '; ') + $(if ($drift.Count -eq 0) { 'in sync' } else { '' }))

# C11 -- the skill bundle ships its own copy of the always-on header, which the model can read
# on demand. helper-core-B fixed the diff narrative in helper-rs/assets/prompts/dsh-header.md
# while the skill copy kept the old text, so the model could still read a contract that no
# longer exists. A copy that is *allowed* to drift is a second source of truth.
$headerAsset = Join-Path $root 'helper-rs\assets\prompts\dsh-header.md'
$headerSkill = Join-Path $root 'skills\computer-use\references\dsh-header.md'
$headerSame = $false
if ((Test-Path $headerAsset) -and (Test-Path $headerSkill)) {
  $headerSame = (Get-FileHash -LiteralPath $headerAsset -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $headerSkill -Algorithm SHA256).Hash
}
$c11ev = if ($headerSame) { 'identical' } else { 'skill reference copy differs from the helper asset' }
Claim 'C11' 'skill header copy matches the helper asset' $headerSame $c11ev

# C12 -- the two browser reference documents the plugin ships must be the official bytes
# (PSG-4). They were delivered during the 2026-09-14 fixes; without this claim a later edit
# could silently reword a confirmation policy the model is supposed to follow verbatim.
$browserOfficial = ($CodexHome + '\plugins\cache\openai-bundled\browser\26.903.61454\docs')
$browserRefs = @{ 'browser-safety.md' = 'browser-safety.md'; 'confirmations.md' = 'confirmations.md' }
$browserSame = 0
$browserDrift = @()
foreach ($name in $browserRefs.Keys) {
  # Browser policy belongs to the browser skill, not the desktop one (the first version of this
  # claim looked in `computer-use/references` and reported a drift that did not exist).
  $ours = Join-Path $root ('skills\computer-use-browser\references\' + $name)
  $theirs = Join-Path $browserOfficial $browserRefs[$name]
  if ((Test-Path $ours) -and (Test-Path $theirs) -and ((Get-FileHash -LiteralPath $ours -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $theirs -Algorithm SHA256).Hash)) {
    $browserSame++
  } else { $browserDrift += $name }
}
$c12ev = if ($browserDrift.Count -eq 0) { 'both browser references byte-identical to the official package' } else { 'drift: ' + ($browserDrift -join ',') }
Claim 'C12' 'browser policy references are the official bytes' ($browserSame -eq 2) $c12ev

$red = @($results | Where-Object { -not $_.ok })
Write-Output ''
Write-Output ('claim audit: ' + ($results.Count - $red.Count) + '/' + $results.Count + ' hold; RED = ' + (($red | ForEach-Object { $_.id }) -join ', '))
if ($red.Count -gt 0) { exit 1 }