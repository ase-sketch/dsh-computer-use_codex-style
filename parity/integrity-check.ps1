# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Continue"
Write-Output "=== 1) source integrity ==="
$files = @(
  "$RepoRoot\helper-rs\src\overlay\mod.rs",
  "$RepoRoot\helper-rs\src\overlay\motion.rs",
  "$RepoRoot\helper-rs\src\interrupt.rs",
  "$RepoRoot\helper-rs\src\tools.rs",
  "$RepoRoot\helper-rs\src\uia.rs",
  "$RepoRoot\helper-rs\src\policy.rs",
  "$RepoRoot\helper-rs\src\protocol.rs",
  "$RepoRoot\helper-rs\src\prompt.rs",
  "$RepoRoot\helper-rs\src\state.rs",
  "$RepoRoot\helper-rs\src\desktop.rs",
  "$RepoRoot\helper-rs\assets\prompts\dsh-header.md",
  "$RepoRoot\src\sidecar.js",
  "$RepoRoot\src\tool.js",
  "$RepoRoot\src\prompt.js",
  "$RepoRoot\src\index.js",
  "$RepoRoot\skills\computer-use\SKILL.md",
  "$RepoRoot\computer_use\browser_schemas.py",
  "$RepoRoot\computer_use\browser_security.py",
  "$RepoRoot\computer_use\browser_checks.py",
  "$RepoRoot\tests\test_parity.py"
)
$missing = @($files | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -gt 0) { Write-Output ("  MISSING: " + ($missing -join ", ")) } else { Write-Output ("  all " + $files.Count + " artifacts present") }
Write-Output ""
Write-Output "=== 2) release binary freshness ==="
$exe = Get-Item "$RepoRoot\helper-rs\target\release\dsh-computer-use.exe"
$newest = Get-ChildItem -Recurse -File "$RepoRoot\helper-rs\src","$RepoRoot\helper-rs\assets" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Output ("  exe        : " + $exe.LastWriteTime)
Write-Output ("  newest src : " + $newest.LastWriteTime + "  (" + $newest.Name + ")")
Write-Output ("  fresh      : " + ($exe.LastWriteTime -ge $newest.LastWriteTime))
Write-Output ""
Write-Output "=== 3) skill reference bundles ==="
$assets = "$RepoRoot\helper-rs\assets\prompts"
foreach ($root in @("$RepoRoot\skills\computer-use","$DshHome\.agent-presets\computer-use\skills\computer-use","$DshHome\skills\computer-use")) {
  $bad = @()
  foreach ($n in @("guidance.md","api.md","confirmations.md")) {
    $a = (Get-FileHash (Join-Path $assets $n)).Hash
    $r = Join-Path $root ("references\" + $n)
    if (-not (Test-Path -LiteralPath $r)) { $bad += ($n + ":absent"); continue }
    $b = (Get-FileHash $r).Hash
    if ($a -ne $b) { $bad += ($n + ":drift") }
  }
  $status = if ($bad.Count -eq 0) { "OK   " } else { "BAD  " }
  Write-Output ("  " + $status + $root + $(if ($bad.Count) { "  -> " + ($bad -join ",") } else { "" }))
}