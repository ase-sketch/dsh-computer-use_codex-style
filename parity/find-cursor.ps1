# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$a = [System.Drawing.Bitmap]::FromFile("$RepoRoot\parity\fix1-before.jpg")
$b = [System.Drawing.Bitmap]::FromFile("$RepoRoot\parity\fix1-after.jpg")
$targets = @(@(14,44,71), @(7,22,36), @(5,15,24), @(8,8,8), @(191,191,191))
function CountSig($img) {
  $n = 0
  for ($y = 0; $y -lt $img.Height; $y++) {
    for ($x = 0; $x -lt $img.Width; $x++) {
      $p = $img.GetPixel($x, $y)
      foreach ($t in $targets) {
        if ([math]::Abs($p.R - $t[0]) -le 3 -and [math]::Abs($p.G - $t[1]) -le 3 -and [math]::Abs($p.B - $t[2]) -le 3) { $n++; break }
      }
    }
  }
  return $n
}
$nb = CountSig $b
$na = CountSig $a
Write-Output ("cursor-signature pixels  BEFORE=" + $na + "   AFTER=" + $nb)
$minX=99999;$maxX=-1;$minY=99999;$maxY=-1;$n=0
for ($y = 0; $y -lt $a.Height; $y++) {
  for ($x = 0; $x -lt $a.Width; $x++) {
    $pa = $a.GetPixel($x,$y)
    $pb = $b.GetPixel($x,$y)
    $d = [math]::Abs($pa.R-$pb.R)+[math]::Abs($pa.G-$pb.G)+[math]::Abs($pa.B-$pb.B)
    if ($d -gt 30) {
      $n++
      if ($x -lt $minX) { $minX = $x }
      if ($x -gt $maxX) { $maxX = $x }
      if ($y -lt $minY) { $minY = $y }
      if ($y -gt $maxY) { $maxY = $y }
    }
  }
}
Write-Output ("changed pixels: " + $n + "  bbox " + $minX + "," + $minY + " .. " + $maxX + "," + $maxY)
$a.Dispose()
$b.Dispose()