# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Stop"
$csc = $null
foreach ($root in @("C:\Windows\Microsoft.NET\Framework64","C:\Windows\Microsoft.NET\Framework")) {
  if ($csc) { break }
  $csc = Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName "csc.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
}
Write-Output ("csc = " + $csc)
$out = "$RepoRoot\parity\ParityTarget.exe"
& $csc /nologo /target:winexe /out:$out /reference:System.Windows.Forms.dll /reference:System.Drawing.dll "$RepoRoot\parity\ParityTarget.cs.txt" 2>&1 | Select-Object -First 12
if (Test-Path $out) { Write-Output ("built: " + (Get-Item $out).Length + " bytes") } else { Write-Output "BUILD FAILED" }