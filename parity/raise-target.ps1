# Restore the parity target to a known, fully on-screen geometry and raise it.
#
# The target is a DPI-unaware WinForms app (design size 640x420 at 240,180), so on a
# 150% display its physical rect is 960x630 at 360,270. This script must therefore be
# per-monitor DPI aware and must pass PHYSICAL coordinates.
#
# NOTE: the handle variable is `$hwnd`, not `$h`. PowerShell variable names are
# case-insensitive, so `$h` silently overwrote the `$H` height parameter and the window
# was resized to the handle's numeric value.
param([int]$X = 360, [int]$Y = 270, [int]$W = 960, [int]$H = 630)
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Zr {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
'@
[void][Zr]::SetProcessDpiAwarenessContext([IntPtr](-4))
$p = Get-Process ParityTarget -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Write-Output 'ParityTarget is not running'; exit 1 }
$hwnd = $p.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { $p.Refresh(); $hwnd = $p.MainWindowHandle }
if ($hwnd -eq [IntPtr]::Zero) { Write-Output 'no main window handle'; exit 1 }
[void][Zr]::ShowWindow($hwnd, 9)
Start-Sleep -Milliseconds 300
# HWND_TOP=0, SWP_NOACTIVATE|SWP_SHOWWINDOW = 0x0010|0x0040
$ok = [Zr]::SetWindowPos($hwnd, [IntPtr]::Zero, $X, $Y, $W, $H, 0x0050)
Start-Sleep -Milliseconds 350
$vw = [Zr]::GetSystemMetrics(78); $vh = [Zr]::GetSystemMetrics(79)
$r = New-Object Zr+RECT
[void][Zr]::GetWindowRect($hwnd, [ref]$r)
$matched = (($r.Right - $r.Left) -eq $W) -and (($r.Bottom - $r.Top) -eq $H) -and ($r.Left -eq $X) -and ($r.Top -eq $Y)
$onScreen = ($r.Left -ge 0) -and ($r.Top -ge 0) -and ($r.Right -le $vw) -and ($r.Bottom -le $vh)
Write-Output ('target hwnd=' + $hwnd + ' ok=' + $ok + ' asked=' + $X + ',' + $Y + ' ' + $W + 'x' + $H + ' rect=' + $r.Left + ',' + $r.Top + ' ' + ($r.Right - $r.Left) + 'x' + ($r.Bottom - $r.Top) + ' matched=' + $matched + ' fullyOnScreen=' + $onScreen)