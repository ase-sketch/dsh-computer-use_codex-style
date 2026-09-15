# Inject an untagged key press. After the tag-based fix, an untagged event is exactly
# what a physical key looks like to the helper's low-level hook, so this drives the
# same Escape-interrupt path a human would.
param([int]$Vk = 0x1B, [int]$DelayMs = 900)
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class InjectedKey {
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  public const uint KEYUP = 0x0002;
}
'@
Start-Sleep -Milliseconds $DelayMs
[InjectedKey]::keybd_event([byte]$Vk, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 40
[InjectedKey]::keybd_event([byte]$Vk, 0, [InjectedKey]::KEYUP, [UIntPtr]::Zero)
Write-Output ('key 0x' + $Vk.ToString('X2') + ' sent')