# Is the real system pointer actually invisible right now?
#
# SetSystemCursor keeps the cursor HANDLE and replaces its contents, so comparing
# GetCursorInfo().hCursor with LoadCursor(IDC_ARROW) proves nothing (verified: after a
# manual SetSystemCursor(blank) the handle is unchanged). The reliable signal is the
# icon's colour bitmap: a blanked pointer becomes monochrome (hbmColor == 0).
param([switch]$Quiet)
$ErrorActionPreference='Continue'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class CurSup {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] public struct CURSORINFO { public int cbSize; public int flags; public IntPtr hCursor; public POINT pt; }
  [StructLayout(LayoutKind.Sequential)] public struct ICONINFO { public bool fIcon; public int xHotspot; public int yHotspot; public IntPtr hbmMask; public IntPtr hbmColor; }
  [DllImport("user32.dll")] public static extern bool GetCursorInfo(ref CURSORINFO ci);
  [DllImport("user32.dll")] public static extern bool GetIconInfo(IntPtr h, ref ICONINFO ii);
  public static bool Suppressed() {
    CURSORINFO ci = new CURSORINFO(); ci.cbSize = Marshal.SizeOf(typeof(CURSORINFO));
    if (!GetCursorInfo(ref ci)) return false;
    if (ci.hCursor == IntPtr.Zero) return true;
    ICONINFO ii = new ICONINFO();
    GetIconInfo(ci.hCursor, ref ii);
    return ii.hbmColor == IntPtr.Zero;
  }
  public static long Handle() { CURSORINFO ci = new CURSORINFO(); ci.cbSize = Marshal.SizeOf(typeof(CURSORINFO)); GetCursorInfo(ref ci); return ci.hCursor.ToInt64(); }
}
'@
$suppressed = [CurSup]::Suppressed()
if ($Quiet) { if ($suppressed) { 'suppressed' } else { 'visible' } } else {
  ([pscustomobject]@{ suppressed = $suppressed; hCursor = ('0x{0:X}' -f [CurSup]::Handle()) } | ConvertTo-Json -Compress)
}