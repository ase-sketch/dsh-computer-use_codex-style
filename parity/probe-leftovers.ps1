# Read-only leftovers probe (no kills, no writes).
Add-Type -Namespace CuProbe -Name Native -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
[StructLayout(LayoutKind.Sequential)] public struct CURSORINFO { public int cbSize; public int flags; public IntPtr hCursor; public POINT ptScreenPos; }
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int x; public int y; }
[StructLayout(LayoutKind.Sequential)] public struct ICONINFO { public bool fIcon; public int xHotspot; public int yHotspot; public IntPtr hbmMask; public IntPtr hbmColor; }
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr p);
[DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, ref RECT r);
[DllImport("user32.dll")] public static extern long GetWindowLongPtr(IntPtr h, int i);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool GetCursorInfo(ref CURSORINFO ci);
[DllImport("user32.dll")] public static extern bool GetIconInfo(IntPtr h, ref ICONINFO ii);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr p);
'@
$all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
$helpers = $all | Where-Object { $_.Name -match 'dsh-computer-use|codex-computer-use' -and $_.CommandLine -notmatch '--system-cursor-manager' }
$managers = $all | Where-Object { $_.CommandLine -match '--system-cursor-manager' }
Write-Output ('HELPERS=' + ($helpers | Measure-Object).Count)
foreach ($h in $helpers) { Write-Output ('  helper pid=' + $h.ProcessId + ' parent=' + $h.ParentProcessId + ' cmd=' + ($h.CommandLine -replace '\s+',' ')) }
Write-Output ('MANAGERS=' + ($managers | Measure-Object).Count)
foreach ($m in $managers) { Write-Output ('  manager pid=' + $m.ProcessId + ' parent=' + $m.ParentProcessId) }
$overlays = New-Object System.Collections.ArrayList
$cb = [CuProbe.Native+EnumWindowsProc]{ param($h, $p)
  $sb = New-Object System.Text.StringBuilder 256; [void][CuProbe.Native]::GetClassName($h, $sb, 256); $cls = $sb.ToString()
  if ($cls -like 'Dsh*' -or $cls -like '*ComputerUse*') {
    $t = New-Object System.Text.StringBuilder 256; [void][CuProbe.Native]::GetWindowText($h, $t, 256)
    $r = New-Object CuProbe.Native+RECT; [void][CuProbe.Native]::GetWindowRect($h, [ref]$r)
    $wpid = 0; [void][CuProbe.Native]::GetWindowThreadProcessId($h, [ref]$wpid)
    $vis = [CuProbe.Native]::IsWindowVisible($h)
    [void]$overlays.Add(('  overlay hwnd={0} pid={1} class={2} vis={3} rect=({4},{5})-({6},{7}) title=[{8}]' -f $h, $wpid, $cls, $vis, $r.Left, $r.Top, $r.Right, $r.Bottom, $t.ToString()))
  }
  return $true }
[void][CuProbe.Native]::EnumWindows($cb, [IntPtr]::Zero)
Write-Output ('OVERLAYS=' + $overlays.Count)
$visCount = ($overlays | Where-Object { $_ -match 'vis=True' } | Measure-Object).Count
Write-Output ('OVERLAYS_VISIBLE=' + $visCount)
$overlays | ForEach-Object { $_ }
$ci = New-Object CuProbe.Native+CURSORINFO; $ci.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf([type]'CuProbe.Native+CURSORINFO')
$blanked = 'unknown'
if ([CuProbe.Native]::GetCursorInfo([ref]$ci)) {
  $ii = New-Object CuProbe.Native+ICONINFO
  $ok = [CuProbe.Native]::GetIconInfo($ci.hCursor, [ref]$ii)
  $blanked = ($ok -and ($ii.hbmColor -eq [IntPtr]::Zero))
  Write-Output ('CURSOR pos=({0},{1}) colourBitmap={2} BLANKED={3}' -f $ci.ptScreenPos.x, $ci.ptScreenPos.y, [int64]$ii.hbmColor, $blanked)
} else { Write-Output 'CURSOR unknown' }