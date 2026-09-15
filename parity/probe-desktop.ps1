$ErrorActionPreference = "Continue"
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class D {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern IntPtr GetDesktopWindow();
  [DllImport("user32.dll")] public static extern IntPtr GetShellWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern IntPtr OpenInputDesktop(uint f, bool inherit, uint access);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern bool GetUserObjectInformationW(IntPtr h, int index, StringBuilder buf, uint len, out uint needed);
  [DllImport("user32.dll")] public static extern bool CloseDesktop(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetThreadDesktop(uint tid);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  public delegate bool EnumProc(IntPtr h, IntPtr p);
}
"@
function Name([IntPtr]$h) { $sb = New-Object System.Text.StringBuilder 256; [void][D]::GetClassNameW($h, $sb, 256); $sb.ToString() }
function Title([IntPtr]$h) { $sb = New-Object System.Text.StringBuilder 256; [void][D]::GetWindowTextW($h, $sb, 256); $sb.ToString() }
Write-Output ("fg          = " + [D]::GetForegroundWindow())
Write-Output ("shell       = " + [D]::GetShellWindow() + "  class=" + (Name ([D]::GetShellWindow())))
Write-Output ("desktopWin  = " + [D]::GetDesktopWindow())
$d = [D]::OpenInputDesktop(0, $false, 0x0001)
Write-Output ("OpenInputDesktop = " + $d)
if ($d -ne [IntPtr]::Zero) {
  $sb = New-Object System.Text.StringBuilder 256; $need = 0
  [void][D]::GetUserObjectInformationW($d, 2, $sb, 512, [ref]$need)
  Write-Output ("input desktop name = " + $sb.ToString())
  [void][D]::CloseDesktop($d)
}
$td = [D]::GetThreadDesktop([D]::GetCurrentThreadId())
$sb2 = New-Object System.Text.StringBuilder 256; $n2 = 0
[void][D]::GetUserObjectInformationW($td, 2, $sb2, 512, [ref]$n2)
Write-Output ("thread desktop     = " + $sb2.ToString())
$visible = 0; $titled = 0
$cb = [D+EnumProc]{ param($h, $p) if ([D]::IsWindowVisible($h)) { $script:visible++; if ((Title $h) -ne "") { $script:titled++ } }; return $true }
[void][D]::EnumWindows($cb, [IntPtr]::Zero)
Write-Output ("visible windows    = " + $visible + "  with title = " + $titled)