# Dev helper: raise a window from a thread that is attached to the foreground input queue.
# The old version hardcoded a window handle and could not even parse (unescaped quotes in the
# embedded C#), so it is parameterised: pass the handle you want to raise.
param([long]$Target = 0)

$ErrorActionPreference = "Continue"
$src = @'
using System;
using System.Runtime.InteropServices;
public class F {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern IntPtr SetFocus(IntPtr h);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
}
'@
Add-Type -TypeDefinition $src
$fg = [F]::GetForegroundWindow()
$fgPid = 0
$fgThread = [F]::GetWindowThreadProcessId($fg, [ref]$fgPid)
$me = [F]::GetCurrentThreadId()
Write-Output ("fg=" + $fg + " fgThread=" + $fgThread + " me=" + $me)
if ($Target -eq 0) { Write-Output 'no -Target handle given; reporting only'; exit 0 }
$handle = [IntPtr]::new($Target)
if ($fgThread -ne 0) { [void][F]::AttachThreadInput($me, $fgThread, $true) }
[void][F]::ShowWindow($handle, 9)
[void][F]::BringWindowToTop($handle)
[void][F]::SetForegroundWindow($handle)
[void][F]::SetFocus($handle)
if ($fgThread -ne 0) { [void][F]::AttachThreadInput($me, $fgThread, $false) }
Start-Sleep -Milliseconds 700
Write-Output ("after: fg=" + [F]::GetForegroundWindow())
