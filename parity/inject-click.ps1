# Inject an untagged mouse click at a screen point. This stands in for a real human
# click in environments where the operator's input already arrives injected (remote
# desktop / VM console): the helper distinguishes *its own* injections by the
# dwExtraInfo tag, so an untagged click is treated exactly like a physical one.
param([int]$X = 300, [int]$Y = 300)
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class InjectedClick {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  public const uint LEFTDOWN = 0x0002;
  public const uint LEFTUP = 0x0004;
}
'@
[void][InjectedClick]::SetProcessDpiAwarenessContext([IntPtr](-4))
[void][InjectedClick]::SetCursorPos($X, $Y)
Start-Sleep -Milliseconds 150
[InjectedClick]::mouse_event([InjectedClick]::LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 40
[InjectedClick]::mouse_event([InjectedClick]::LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
Write-Output "clicked $X,$Y"