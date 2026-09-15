# Raise the DSH browser window over the parity target without activating anything, to test
# that capturing the *target window* still works while it is occluded on screen.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Oc {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
'@
[void][Oc]::SetProcessDpiAwarenessContext([IntPtr](-4))
$browser = Get-Process msedge -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $browser) { Write-Output 'no browser window to occlude with'; exit 0 }
$hwnd = $browser.MainWindowHandle
# HWND_TOP=0, SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_SHOWWINDOW
[void][Oc]::SetWindowPos($hwnd, [IntPtr]::Zero, 0, 0, 0, 0, 0x0053)
Start-Sleep -Milliseconds 400
$r = New-Object Oc+RECT
[void][Oc]::GetWindowRect($hwnd, [ref]$r)
Write-Output ('occluder msedge rect=' + $r.Left + ',' + $r.Top + ' ' + ($r.Right - $r.Left) + 'x' + ($r.Bottom - $r.Top))