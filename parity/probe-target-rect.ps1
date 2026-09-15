Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class W {
  [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
'@
[void][W]::SetProcessDpiAwarenessContext([IntPtr](-4))
$p = Get-Process ParityTarget | Select-Object -First 1; $p.Refresh(); $h = $p.MainWindowHandle
$r = New-Object W+RECT; [void][W]::GetWindowRect($h, [ref]$r)
Write-Output ('before: zoomed=' + [W]::IsZoomed($h) + ' iconic=' + [W]::IsIconic($h) + ' rect=' + $r.Left + ',' + $r.Top + ' ' + ($r.Right-$r.Left) + 'x' + ($r.Bottom-$r.Top))
[void][W]::ShowWindow($h, 9)
Start-Sleep -Milliseconds 300
$r2 = New-Object W+RECT; [void][W]::GetWindowRect($h, [ref]$r2)
Write-Output ('after restore: zoomed=' + [W]::IsZoomed($h) + ' rect=' + $r2.Left + ',' + $r2.Top + ' ' + ($r2.Right-$r2.Left) + 'x' + ($r2.Bottom-$r2.Top))
[void][W]::SetWindowPos($h, [IntPtr]::Zero, 360, 270, 960, 630, 0x0050)
Start-Sleep -Milliseconds 300
$r3 = New-Object W+RECT; [void][W]::GetWindowRect($h, [ref]$r3)
Write-Output ('after setpos: zoomed=' + [W]::IsZoomed($h) + ' rect=' + $r3.Left + ',' + $r3.Top + ' ' + ($r3.Right-$r3.Left) + 'x' + ($r3.Bottom-$r3.Top))