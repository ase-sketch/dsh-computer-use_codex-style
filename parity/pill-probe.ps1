# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Generic;
public static class OverlayProbe {
  public delegate bool EnumProc(IntPtr hwnd, IntPtr lparam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lparam);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd, StringBuilder buf, int max);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern bool SetWindowDisplayAffinity(IntPtr hwnd, uint affinity);
  [DllImport("user32.dll")] public static extern bool GetWindowDisplayAffinity(IntPtr hwnd, out uint affinity);
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
  public static List<IntPtr> FindAll(string cls) {
    var found = new List<IntPtr>();
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      var sb = new StringBuilder(256);
      GetClassName(h, sb, 256);
      if (sb.ToString() == cls) found.Add(h);
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
'@
[void][OverlayProbe]::SetProcessDpiAwarenessContext([IntPtr](-4))
$targets = [OverlayProbe]::FindAll('DshComputerUseCursorOverlay')
if ($targets.Count -eq 0) { Write-Output 'banner window not found'; exit 1 }
foreach ($h in $targets) {
  $pid2 = 0; [void][OverlayProbe]::GetWindowThreadProcessId($h, [ref]$pid2)
  $before = 0; [void][OverlayProbe]::GetWindowDisplayAffinity($h, [ref]$before)
  [void][OverlayProbe]::SetWindowDisplayAffinity($h, 0)
  Write-Output "banner hwnd=$h pid=$pid2 visible=$([OverlayProbe]::IsWindowVisible($h)) affinity=$before -> 0"
}
Start-Sleep -Milliseconds 400
$x = [OverlayProbe]::GetSystemMetrics(76); $y = [OverlayProbe]::GetSystemMetrics(77)
$w = [OverlayProbe]::GetSystemMetrics(78); $h2 = [OverlayProbe]::GetSystemMetrics(79)
$bmp = New-Object System.Drawing.Bitmap $w, $h2
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size $w, $h2))
$g.Dispose()
$out = ($RepoRoot + '/parity/pill-visible.png')
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
foreach ($h in $targets) { [void][OverlayProbe]::SetWindowDisplayAffinity($h, 17) }
Write-Output "saved $out (${w}x${h2})"