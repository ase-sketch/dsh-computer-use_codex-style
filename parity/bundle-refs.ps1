# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Stop"
$skillRoots = @(
  "$RepoRoot\skills\computer-use",
  "$DshHome\.agent-presets\computer-use\skills\computer-use",
  "$DshHome\skills\computer-use"
)
$assets = "$RepoRoot\helper-rs\assets\prompts"
foreach ($root in $skillRoots) {
  if (-not (Test-Path -LiteralPath $root)) { New-Item -ItemType Directory -Force -Path $root | Out-Null }
  $refs = Join-Path $root "references"
  New-Item -ItemType Directory -Force -Path $refs | Out-Null
  foreach ($name in @("guidance.md","api.md","confirmations.md","dsh-header.md")) {
    Copy-Item -LiteralPath (Join-Path $assets $name) -Destination (Join-Path $refs $name) -Force
  }
  Write-Output ("bundled: " + $root)
}
Write-Output ""
Get-ChildItem -Recurse -File "$RepoRoot\skills\computer-use" | Select-Object @{n="rel";e={$_.FullName.Replace("$RepoRoot\skills\computer-use\","")}},Length | Format-Table -AutoSize | Out-String -Width 140