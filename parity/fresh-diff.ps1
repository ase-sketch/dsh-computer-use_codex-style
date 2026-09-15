# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

Add-Type -AssemblyName System.Drawing
function Pixels($name) {
  $src = New-Object System.Drawing.Bitmap ("$RepoRoot/parity/$name")
  $w = $src.Width; $h = $src.Height
  $rect = New-Object System.Drawing.Rectangle 0,0,$w,$h
  $d = $src.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $b = New-Object byte[] ($d.Stride * $h)
  [System.Runtime.InteropServices.Marshal]::Copy($d.Scan0, $b, 0, $b.Length)
  $src.UnlockBits($d); $src.Dispose()
  return @{ bytes = $b; stride = $d.Stride; w = $w; h = $h }
}
$a = Pixels 'fresh-0.jpg'; $b = Pixels 'fresh-1.jpg'; $c = Pixels 'fresh-2.jpg'
function RegionDiff($a, $b, $x0, $y0, $x1, $y1, $label) {
  $n = 0
  for ($y = $y0; $y -lt $y1; $y++) {
    for ($x = $x0; $x -lt $x1; $x++) {
      $i = $y * $a.stride + $x * 4
      $dr = [Math]::Abs([int]$a.bytes[$i] - [int]$b.bytes[$i])
      $dg = [Math]::Abs([int]$a.bytes[$i+1] - [int]$b.bytes[$i+1])
      $db = [Math]::Abs([int]$a.bytes[$i+2] - [int]$b.bytes[$i+2])
      if (($dr + $dg + $db) -gt 60) { $n++ }
    }
  }
  Write-Output "$label differing pixels: $n"
}
RegionDiff $a $b 60 130 620 180 'textbox fresh-0 -> fresh-1'
RegionDiff $a $c 60 130 620 180 'textbox fresh-0 -> fresh-2'
RegionDiff $b $c 60 130 620 180 'textbox fresh-1 -> fresh-2'
RegionDiff $b $c 60 60 950 130 'header fresh-1 -> fresh-2'