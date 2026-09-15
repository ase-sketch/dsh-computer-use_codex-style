$ErrorActionPreference = "Continue"
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
}
"@
$h = [W]::GetForegroundWindow()
Write-Output ("hwnd=" + $h)
$pid2 = 0
[void][W]::GetWindowThreadProcessId($h, [ref]$pid2)
Write-Output ("pid=" + $pid2)
$sb = New-Object System.Text.StringBuilder 512
[void][W]::GetWindowTextW($h, $sb, 512)
Write-Output ("title=" + $sb.ToString())
$cb = New-Object System.Text.StringBuilder 512
[void][W]::GetClassNameW($h, $cb, 512)
Write-Output ("class=" + $cb.ToString())
Write-Output ("sessionId(self)=" + (Get-Process -Id $PID).SessionId)
$fg = Get-Process -Id $pid2 -ErrorAction SilentlyContinue
if ($fg) { Write-Output ("fgProc=" + $fg.ProcessName + " session=" + $fg.SessionId) }