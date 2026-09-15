param([int]$pidFilter = 0)
# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Continue"
Add-Type -TypeDefinition ([System.IO.File]::ReadAllText("$RepoRoot\parity\Z.cs.txt"))
$rows = @()
$cb = [Z+EnumProc]{ param($w, $p)
  $sb = New-Object System.Text.StringBuilder 256
  [void][Z]::GetClassNameW($w, $sb, 256)
  if ($sb.ToString() -eq "DshComputerUseCursorOverlayPointer") {
    $own = 0; [void][Z]::GetWindowThreadProcessId($w, [ref]$own)
    if ($pidFilter -eq 0 -or $own -eq $pidFilter) {
      $r = New-Object Z+RECT; [void][Z]::GetWindowRect($w, [ref]$r)
      $aff = 0; [void][Z]::GetWindowDisplayAffinity($w, [ref]$aff)
      $script:rows += [pscustomobject]@{ hwnd = $w; pid = $own; L = $r.L; T = $r.T; W = ($r.R-$r.L); H = ($r.B-$r.T); affinity = ("0x{0:X8}" -f $aff) }
    }
  }
  return $true
}
[void][Z]::EnumWindows($cb, [IntPtr]::Zero)
if ($rows.Count -eq 0) { Write-Output ("no cursor overlay window for pid filter " + $pidFilter); exit 0 }
# The window created by the process we care about is the last one enumerated in top-level order.
$row = $rows[-1]
Write-Output ("cursor window pid=" + $row.pid + " hwnd=" + $row.hwnd + " at " + $row.L + "," + $row.T + " " + $row.W + "x" + $row.H + " affinity=" + $row.affinity)
$dc = [Z]::GetDC([IntPtr]::Zero)
$cx = $row.L + 30; $cy = $row.T + 40
$found = $false
for ($y = $row.T; $y -lt ($row.T + $row.H); $y++) {
  for ($x = $row.L; $x -lt ($row.L + $row.W); $x++) {
    $c = [Z]::GetPixel($dc, $x, $y)
    $bb = $c -band 0xFF; $gg = ($c -shr 8) -band 0xFF; $rr = ($c -shr 16) -band 0xFF
    # the glyph fill is #080808 with a white stroke; look for near-white pixels
    if ($rr -gt 200 -and $gg -gt 200 -and $bb -gt 200 -and -not ($rr -eq 240 -and $gg -eq 240)) {
      Write-Output ("  glyph-ish pixel #" + ("{0:X2}{1:X2}{2:X2}" -f $rr, $gg, $bb) + " at " + $x + "," + $y)
      $found = $true; break
    }
  }
  if ($found) { break }
}
[void][Z]::ReleaseDC([IntPtr]::Zero, $dc)
if (-not $found) { Write-Output "  no glyph-coloured pixel found inside the cursor window rect" }