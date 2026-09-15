# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
function Load($p) { $b = [System.Drawing.Bitmap]::FromFile($p); return $b }
$a = Load "$RepoRoot\parity\fix1-before.jpg"
$b = Load "$RepoRoot\parity\fix1-after.jpg"
Write-Output ("sizes: " + $a.Width + "x" + $a.Height + " vs " + $b.Width + "x" + $b.Height)
$diff = 0; $maxDiff = 0; $sumX = 0; $sumY = 0; $n = 0
$minX = 99999; $maxX = -1; $minY = 99999; $maxY = -1
for ($y = 0; $y -lt $a.Height; $y++) {
  for ($x = 0; $x -lt $a.Width; $x++) {
    $pa = $a.GetPixel($x, $y); $pb = $b.GetPixel($x, $y)
    $d = [math]::Abs($pa.R - $pb.R) + [math]::Abs($pa.G - $pb.G) + [math]::Abs($pa.B - $pb.B)
    if ($d -gt 30) {
      $diff++; $n++; $sumX += $x; $sumY += $y
      if ($x -lt $minX) { $minX = $x }; if ($x -gt $maxX) { $maxX = $x }
      if ($y -lt $minY) { $minY = $y }; if ($y -gt $maxY) { $maxY = $y }
      if ($d -gt $maxDiff) { $maxDiff = $d }
    }
  }
}
Write-Output ("differing pixels (sum|d|>30): " + $diff)
if ($n -gt 0) {
  Write-Output ("  centroid: " + [math]::Round($sumX/$n,1) + "," + [math]::Round($sumY/$n,1))
  Write-Output ("  bbox: " + $minX + "," + $minY + " .. " + $maxX + "," + $maxY)
  Write-Output ("  max channel sum diff: " + $maxDiff)
}
# Expected cursor position in image coordinates: click was at window centre.
Write-Output ("expected cursor at image 480,315 (window centre)")
# Sample the expected cursor neighbourhood in both images for the #080808 signature.
foreach ($pt in @(@(480,315), @(481,316), @(478,312))) {
  $pa = $a.GetPixel($pt[0], $pt[1]); $pb = $b.GetPixel($pt[0], $pt[1])
  Write-Output ("  px " + $pt[0] + "," + $pt[1] + "  before=(" + $pa.R + "," + $pa.G + "," + $pa.B + ")  after=(" + $pb.R + "," + $pb.G + "," + $pb.B + ")")
}
$a.Dispose(); $b.Dispose()