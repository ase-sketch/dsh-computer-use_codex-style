# Count the accent body of the status pill in the captured desktop.
#
# The first version scanned a hardcoded window (x 1028..1534, y 14..64) that encoded the
# PRE-FIX geometry (margin 8*s, height 36*s). When the pill moved to the official geometry
# (margin 56*s, body 48*s) the accent landed at y 84..156 and the window missed it entirely --
# reporting 0 pixels while the pill was on screen the whole time (the overlay agent proved it
# with a wide scan: accent=32406 in the same PNG). A gate must not hardcode the geometry it is
# supposed to verify, so this one derives the bounding box from the image and reports it.
# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

Add-Type -AssemblyName System.Drawing
$src = New-Object System.Drawing.Bitmap ($RepoRoot + '/parity/pill-visible.png')
# The pill pulses between full and 0.76 opacity, so body pixels are the accent either pure or
# blended with whatever is behind it. Both are far more saturated than the teal browser chrome,
# which is what this discriminates on.
$n = 0; $minX = 99999; $maxX = -1; $minY = 99999; $maxY = -1; $sample = ''
$w = $src.Width; $h = $src.Height
# Generous strip: the pill is top-centred on the primary monitor. Widening this costs a second
# of GetPixel calls and removes a whole class of silent misses.
$x0 = [Math]::Max(0, [int]($w * 0.18)); $x1 = [Math]::Min($w, [int]($w * 0.82))
$y0 = 0; $y1 = [Math]::Min($h, 320)
for ($y = $y0; $y -lt $y1; $y += 2) {
  for ($x = $x0; $x -lt $x1; $x += 2) {
    $c = $src.GetPixel($x, $y)
    if (($c.B - $c.R) -gt 150 -and $c.B -gt 180) {
      $n++
      if ($sample -eq '') { $sample = ($c.R.ToString() + ',' + $c.G.ToString() + ',' + $c.B.ToString()) }
      if ($x -lt $minX) { $minX = $x }
      if ($x -gt $maxX) { $maxX = $x }
      if ($y -lt $minY) { $minY = $y }
      if ($y -gt $maxY) { $maxY = $y }
    }
  }
}
if ($n -gt 0) {
  Write-Output ('pill pixels: ' + $n + ' bbox=(' + $minX + ',' + $minY + ')-(' + $maxX + ',' + $maxY + ') sample=' + $sample + ' scan=(' + $x0 + ',' + $y0 + ')-(' + $x1 + ',' + $y1 + ')')
} else {
  Write-Output ('pill pixels: 0 scan=(' + $x0 + ',' + $y0 + ')-(' + $x1 + ',' + $y1 + ')')
}
# Evidence crop follows the measured bbox (never a hardcoded rect), so the saved image always
# shows the pill whenever the count is non-zero.
$pad = 12
$cx = [Math]::Max(0, $minX - $pad); $cy = [Math]::Max(0, $minY - $pad)
$cw = [Math]::Min($w - $cx, [Math]::Max(1, ($maxX - $minX) + 2 * $pad))
$ch = [Math]::Min($h - $cy, [Math]::Max(1, ($maxY - $minY) + 2 * $pad))
if ($n -eq 0) { $cx = [Math]::Max(0, [int]($w * 0.35)); $cy = 0; $cw = [Math]::Min($w - $cx, 600); $ch = [Math]::Min($h, 200) }
$crop = New-Object System.Drawing.Bitmap $cw, $ch
$g = [System.Drawing.Graphics]::FromImage($crop)
$rect = New-Object System.Drawing.Rectangle $cx, $cy, $cw, $ch
$dest = New-Object System.Drawing.Rectangle 0, 0, $cw, $ch
$g.DrawImage($src, $dest, $rect, [System.Drawing.GraphicsUnit]::Pixel)
$g.Dispose()
$crop.Save(($RepoRoot + '/parity/pill-exact.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$crop.Dispose(); $src.Dispose()