# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$p = "$RepoRoot\helper-rs\src\overlay\mod.rs"
$lines = [System.IO.File]::ReadAllLines($p)
$impl = [System.IO.File]::ReadAllLines("$RepoRoot\parity\shimmer-impl.rs.txt")
# keep 0..2045 (through end of attach_display), drop the broken 2046..2116, keep 2117..
$out = @()
$out += $lines[0..2045]
$out += $impl
$out += $lines[2117..($lines.Length-1)]
[System.IO.File]::WriteAllLines($p, $out)
"new line count = " + $out.Length