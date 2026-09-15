# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Continue"
Add-Type -TypeDefinition ([System.IO.File]::ReadAllText("$RepoRoot\parity\O.cs.txt"))
$found = @()
$cb = [O+EnumProc]{ param($h, $p)
  $sb = New-Object System.Text.StringBuilder 256
  [void][O]::GetClassNameW($h, $sb, 256)
  $cls = $sb.ToString()
  if ($cls -like "*CursorOverlay*") {
    $tb = New-Object System.Text.StringBuilder 256
    [void][O]::GetWindowTextW($h, $tb, 256)
    $aff = 0
    [void][O]::GetWindowDisplayAffinity($h, [ref]$aff)
    $r = New-Object O+RECT
    [void][O]::GetWindowRect($h, [ref]$r)
    $script:found += [pscustomobject]@{
      hwnd = $h; class = $cls; title = $tb.ToString();
      visible = [O]::IsWindowVisible($h);
      exStyle = ("0x{0:X8}" -f [O]::GetWindowLongW($h, -20));
      affinity = ("0x{0:X8}" -f $aff);
      rect = ("{0},{1} {2}x{3}" -f $r.L, $r.T, ($r.R - $r.L), ($r.B - $r.T))
    }
  }
  return $true
}
[void][O]::EnumWindows($cb, [IntPtr]::Zero)
if ($found.Count -eq 0) { Write-Output "no cursor overlay windows found" } else { $found | Format-List | Out-String -Width 200 }
Write-Output "WDA_EXCLUDEFROMCAPTURE = 0x00000011"