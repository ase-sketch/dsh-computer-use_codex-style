# Move the "Parity Target" window to an explicit PHYSICAL screen rectangle.
#
# The process is made per-monitor-DPI-aware first: a DPI-unaware PowerShell has its
# coordinates virtualised by Windows, so "600,0" landed the window at physical 900,0 at
# 150% scaling and the pill-overlap geometry the gate assumes silently did not hold.
param(
  [int]$X = 0,
  [int]$Y = 0,
  [int]$Width = 1200,
  [int]$Height = 600
)
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Mv {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
}
"@
# PER_MONITOR_AWARE_V2 = -4
[void][Mv]::SetProcessDpiAwarenessContext([IntPtr](-4))
$found = [IntPtr]::Zero
$cb = [Mv+EnumProc]{
  param($hw, $l)
  $sb = New-Object System.Text.StringBuilder 256
  [void][Mv]::GetWindowTextW($hw, $sb, 256)
  if ($sb.ToString() -eq 'Parity Target') { $script:found = $hw; return $false }
  return $true
}
[void][Mv]::EnumWindows($cb, [IntPtr]::Zero)
if ($found -eq [IntPtr]::Zero) { Write-Output 'not-found'; exit 1 }
[void][Mv]::ShowWindow($found, 5)
# SWP_NOZORDER(0x0004) | SWP_NOACTIVATE(0x0010)
[void][Mv]::SetWindowPos($found, [IntPtr]::Zero, $X, $Y, $Width, $Height, 0x0014)
Write-Output ('moved ' + $X + ',' + $Y + ' ' + $Width + 'x' + $Height)
