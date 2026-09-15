# Restore the Windows system cursors (what any other process calling
# SystemParametersInfo(SPI_SETCURSORS) does) and report, in this same process, whether
# the pointer became visible again. Used to prove the helper re-asserts suppression while
# its overlay is visible (official `schedule system cursor re-suppression`).
$ErrorActionPreference='Continue'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class CurRestore {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] public struct CURSORINFO { public int cbSize; public int flags; public IntPtr hCursor; public POINT pt; }
  [StructLayout(LayoutKind.Sequential)] public struct ICONINFO { public bool fIcon; public int xHotspot; public int yHotspot; public IntPtr hbmMask; public IntPtr hbmColor; }
  [DllImport("user32.dll")] public static extern bool SystemParametersInfo(uint action, uint param, IntPtr data, uint flags);
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
}
'@
$ok = [CurRestore]::SystemParametersInfo(0x0057, 0, [IntPtr]::Zero, 0)
([pscustomobject]@{ restored = $ok; suppressedRightAfter = [CurRestore]::Suppressed() } | ConvertTo-Json -Compress)