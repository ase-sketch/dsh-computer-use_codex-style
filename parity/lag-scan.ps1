# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

Add-Type -AssemblyName System.Drawing
$out = @()
foreach ($name in @('cursor-trace.jpg','lag-a.jpg','cursor-trace2.jpg')) {
  $src = New-Object System.Drawing.Bitmap ("$RepoRoot/parity/$name")
  $w = $src.Width; $h = $src.Height
  $rect = New-Object System.Drawing.Rectangle 0, 0, $w, $h
  $data = $src.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $stride = $data.Stride
  $bytes = New-Object byte[] ($stride * $h)
  [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)
  $src.UnlockBits($data)
  $minX=99999;$minY=99999;$maxX=-1;$maxY=-1;$n=0
  for ($y = 100; $y -lt 620; $y++) {
    for ($x = 60; $x -lt 950; $x++) {
      $i = $y * $stride + $x * 4
      if ($bytes[$i] -lt 45 -and $bytes[$i+1] -lt 45 -and $bytes[$i+2] -lt 45) { $n++; if($x -lt $minX){$minX=$x}; if($y -lt $minY){$minY=$y}; if($x -gt $maxX){$maxX=$x}; if($y -gt $maxY){$maxY=$y} }
    }
  }
  Write-Output "$name dark n=$n bbox=($minX,$minY)-($maxX,$maxY)"
  $src.Dispose()
}