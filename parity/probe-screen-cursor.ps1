# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Continue"
Add-Type -TypeDefinition ([System.IO.File]::ReadAllText("$RepoRoot\parity\S.cs.txt"))
$h = [IntPtr]::Zero
$cb = [S+EnumProc]{ param($w, $p)
  $sb = New-Object System.Text.StringBuilder 256
  [void][S]::GetClassNameW($w, $sb, 256)
  if ($sb.ToString() -eq "DshComputerUseCursorOverlayPointer") { $script:h = $w }
  return $true
}
[void][S]::EnumWindows($cb, [IntPtr]::Zero)
if ($h -eq [IntPtr]::Zero) { Write-Output "cursor window not found"; exit 0 }
$r = New-Object S+RECT
[void][S]::GetWindowRect($h, [ref]$r)
$aff = 0; [void][S]::GetWindowDisplayAffinity($h, [ref]$aff)
Write-Output ("cursor window at " + $r.L + "," + $r.T + " " + ($r.R-$r.L) + "x" + ($r.B-$r.T) + " affinity=0x" + ("{0:X8}" -f $aff))
# Read the live screen inside the cursor rect and count non-background pixels.
$dc = [S]::GetDC([IntPtr]::Zero)
$total = 0; $distinct = @{}; $samples = @()
for ($y = $r.T; $y -lt $r.B; $y += 2) {
  for ($x = $r.L; $x -lt $r.R; $x += 2) {
    $c = [S]::GetPixel($dc, $x, $y)
    $bb = $c -band 0xFF; $gg = ($c -shr 8) -band 0xFF; $rr = ($c -shr 16) -band 0xFF
    $key = ("{0},{1},{2}" -f $rr, $gg, $bb)
    $total++
    if ($distinct.ContainsKey($key)) { $distinct[$key]++ } else { $distinct[$key] = 1 }
    if ($samples.Count -lt 10 -and -not ($rr -eq 240 -and $gg -eq 240 -and $bb -eq 240)) { $samples += ("#" + ("{0:X2}{1:X2}{2:X2}" -f $rr, $gg, $bb) + "@" + $x + "," + $y) }
  }
}
[void][S]::ReleaseDC([IntPtr]::Zero, $dc)
Write-Output ("sampled " + $total + " pixels, distinct colours " + $distinct.Count)
Write-Output "top colours:"
$distinct.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 8 | ForEach-Object { "  " + $_.Key + "  x" + $_.Value }
if ($samples.Count) { Write-Output ("non-240 samples: " + ($samples -join " ")) } else { Write-Output "no non-240 pixels: the cursor is NOT rendered on screen" }