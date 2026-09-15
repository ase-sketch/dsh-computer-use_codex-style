param([Parameter(Mandatory=$true)][int]$TargetPid)
$ErrorActionPreference='Continue'
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class CUProbe {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] public struct CURSORINFO { public int cbSize; public int flags; public IntPtr hCursor; public POINT pt; }
  [DllImport("user32.dll")] public static extern bool GetCursorInfo(ref CURSORINFO ci);
  [DllImport("user32.dll")] public static extern IntPtr LoadCursor(IntPtr instance, int name);
}
'@
$wins = New-Object System.Collections.ArrayList
$cb = [CUProbe+EnumProc]{ param($h, $l)
  [uint32]$wp = 0
  [void][CUProbe]::GetWindowThreadProcessId($h, [ref]$wp)
  if ($wp -eq $TargetPid) {
    $sb = New-Object System.Text.StringBuilder 256
    [void][CUProbe]::GetClassName($h, $sb, 256)
    $rc = [CUProbe+RECT]::new()
    [void][CUProbe]::GetWindowRect($h, [ref]$rc)
    [void]$wins.Add([pscustomobject]@{ class = $sb.ToString(); visible = [CUProbe]::IsWindowVisible($h); rect = @($rc.L, $rc.T, ($rc.R - $rc.L), ($rc.B - $rc.T)) })
  }
  return $true
}
[void][CUProbe]::EnumWindows($cb, [IntPtr]::Zero)
$kids = @()
foreach ($k in (Get-CimInstance Win32_Process -Filter "ParentProcessId=$TargetPid" -ErrorAction SilentlyContinue)) {
  $kids += [pscustomobject]@{ pid = $k.ProcessId; name = $k.Name; args = $k.CommandLine }
}
$ci = [CUProbe+CURSORINFO]::new()
$ci.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf([type][CUProbe+CURSORINFO])
$ok = [CUProbe]::GetCursorInfo([ref]$ci)
$arrow = [CUProbe]::LoadCursor([IntPtr]::Zero, 32512)
$report = [pscustomobject]@{
  overlay = @($wins | Where-Object { $_.class -like '*Overlay*' })
  allWindows = @($wins)
  children = @($kids)
  cursor = [pscustomobject]@{ ok = $ok; showing = (($ci.flags -band 1) -ne 0); hCursor = ('0x{0:X}' -f [int64]$ci.hCursor); arrow = ('0x{0:X}' -f [int64]$arrow); sameAsArrow = ($ci.hCursor -eq $arrow); x = $ci.pt.X; y = $ci.pt.Y }
}
$report | ConvertTo-Json -Depth 6 -Compress