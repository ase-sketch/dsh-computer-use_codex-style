# Restore (un-minimize) one window by HWND without clicking anything. The official helper
# refuses a minimized window (`window is minimized; call activate_window, ...`), and the M-C
# sampling agent needed the same step. Used by ax-rich-parity.mjs.
# -Focus additionally brings the window to the foreground, which is how the gate tests the
# official's focused-sentence rule (the sentence only appears while the window is focused).
param([Parameter(Mandatory=$true)][int]$Hwnd, [switch]$Focus)
Add-Type -Namespace DshParity -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
'@
$h = [IntPtr]$Hwnd
$was = [DshParity.Native]::IsIconic($h)
if ($was) { [void][DshParity.Native]::ShowWindow($h, 9) }
$focused = $false
if ($Focus) {
  [void][DshParity.Native]::SetForegroundWindow($h)
  Start-Sleep -Milliseconds 400
  $focused = ([DshParity.Native]::GetForegroundWindow() -eq $h)
}
Write-Output ("hwnd={0} wasIconic={1} nowIconic={2} focused={3}" -f $Hwnd, $was, [DshParity.Native]::IsIconic($h), $focused)