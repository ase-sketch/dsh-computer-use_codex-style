Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class DpiAware {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
}
'@
# -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
[void][DpiAware]::SetProcessDpiAwarenessContext([IntPtr](-4))
$x = [DpiAware]::GetSystemMetrics(76)
$y = [DpiAware]::GetSystemMetrics(77)
$w = [DpiAware]::GetSystemMetrics(78)
$h = [DpiAware]::GetSystemMetrics(79)
Write-Output "virtual screen $x,$y ${w}x${h}"
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size $w, $h))
$g.Dispose()
$out = $args[0]
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "saved $out"