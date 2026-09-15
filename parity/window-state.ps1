# Put the parity target into a specific window state, for the activate/observe edge cases.
#
# The handle is resolved with EnumWindows rather than Process.MainWindowHandle: the latter
# goes stale (returns 0 or another window) once the target is hidden or minimized, which made
# every later state transition a silent no-op.
param([ValidateSet('normal','minimize','hide','offscreen','restore')] [string]$State = 'normal',
      [int]$X = 360, [int]$Y = 270, [int]$W = 960, [int]$H = 630)
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class Ws {
  public delegate bool EnumProc(IntPtr hwnd, IntPtr lparam);
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lparam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int max);
  public struct RECT { public int Left, Top, Right, Bottom; }
  public static IntPtr FindByPid(uint want) {
    IntPtr found = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (pid != want) return true;
      var sb = new StringBuilder(256);
      GetWindowText(h, sb, 256);
      if (sb.ToString() == "Parity Target") { found = h; return false; }
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
'@
[void][Ws]::SetProcessDpiAwarenessContext([IntPtr](-4))
$p = Get-Process ParityTarget -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Write-Output 'ParityTarget is not running'; exit 1 }
$hwnd = [Ws]::FindByPid([uint32]$p.Id)
if ($hwnd -eq [IntPtr]::Zero) { Write-Output 'no Parity Target window for pid'; exit 1 }
switch ($State) {
  'minimize' { [void][Ws]::ShowWindow($hwnd, 6) }   # SW_MINIMIZE
  'hide'     { [void][Ws]::ShowWindow($hwnd, 0) }   # SW_HIDE
  'offscreen'{ [void][Ws]::ShowWindow($hwnd, 5); [void][Ws]::ShowWindow($hwnd, 9); [void][Ws]::SetWindowPos($hwnd, [IntPtr]::Zero, $X, $Y, $W, $H, 0x0050) }
  'restore'  { [void][Ws]::ShowWindow($hwnd, 5); [void][Ws]::ShowWindow($hwnd, 9) }
  default    { [void][Ws]::ShowWindow($hwnd, 5); [void][Ws]::ShowWindow($hwnd, 9); [void][Ws]::SetWindowPos($hwnd, [IntPtr]::Zero, $X, $Y, $W, $H, 0x0050) }
}
Start-Sleep -Milliseconds 500
$r = New-Object Ws+RECT
[void][Ws]::GetWindowRect($hwnd, [ref]$r)
Write-Output ('state=' + $State + ' hwnd=' + $hwnd + ' iconic=' + [Ws]::IsIconic($hwnd) + ' visible=' + [Ws]::IsWindowVisible($hwnd) + ' rect=' + $r.Left + ',' + $r.Top + ' ' + ($r.Right - $r.Left) + 'x' + ($r.Bottom - $r.Top))