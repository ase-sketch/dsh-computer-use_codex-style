# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Continue"
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition ([System.IO.File]::ReadAllText("$RepoRoot\parity\P.cs.txt"))
$cursorHwnd = [IntPtr]::Zero
$cb = [P+EnumProc]{ param($h, $p)
  $sb = New-Object System.Text.StringBuilder 256
  [void][P]::GetClassNameW($h, $sb, 256)
  if ($sb.ToString() -eq "DshComputerUseCursorOverlayPointer") { $script:cursorHwnd = $h }
  return $true
}
[void][P]::EnumWindows($cb, [IntPtr]::Zero)
if ($cursorHwnd -eq [IntPtr]::Zero) { Write-Output "cursor window not found"; exit 0 }
$r = New-Object P+RECT
[void][P]::GetWindowRect($cursorHwnd, [ref]$r)
Write-Output ("cursor window hwnd=" + $cursorHwnd + " rect=" + $r.L + "," + $r.T + " " + ($r.R-$r.L) + "x" + ($r.B-$r.T))
# Capture the cursor window contents via PrintWindow to see whether it draws anything.
$w = $r.R - $r.L; $h = $r.B - $r.T
if ($w -le 0 -or $h -le 0) { Write-Output "empty rect"; exit 0 }
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [P]::PrintWindow($cursorHwnd, $hdc, 0)
$g.ReleaseHdc($hdc)
$g.Dispose()
Write-Output ("PrintWindow returned " + $ok)
# Count non-black pixels (the window is drawn with a black colorkey background).
$nonBlack = 0; $samples = @()
for ($y = 0; $y -lt $h; $y += 2) {
  for ($x = 0; $x -lt $w; $x += 2) {
    $px = $bmp.GetPixel($x, $y)
    if ($px.R -gt 8 -or $px.G -gt 8 -or $px.B -gt 8) {
      $nonBlack++
      if ($samples.Count -lt 6) { $samples += ("(" + $x + "," + $y + ")=#" + ("{0:X2}{1:X2}{2:X2}" -f $px.R, $px.G, $px.B)) }
    }
  }
}
Write-Output ("non-black sampled pixels: " + $nonBlack + " of " + [math]::Floor($w/2) * [math]::Floor($h/2))
if ($samples.Count) { Write-Output ("  samples: " + ($samples -join " ")) }
$bmp.Save("$RepoRoot\parity\cursor-window.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "saved cursor-window.png"