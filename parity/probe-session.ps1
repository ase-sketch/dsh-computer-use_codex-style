# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Continue"
Add-Type -TypeDefinition ([System.IO.File]::ReadAllText("$RepoRoot\parity\T.cs.txt"))
$sid = (Get-Process -Id $PID).SessionId
Write-Output ("active console session  = " + [T]::WTSGetActiveConsoleSessionId())
Write-Output ("current process session = " + $sid)
$names = @("Active","Connected","ConnectQuery","Shadow","Disconnected","Idle","Listen","Reset","Down","Init")
$buf = [IntPtr]::Zero; $len = 0
if ([T]::WTSQuerySessionInformationW([IntPtr]::Zero, $sid, 8, [ref]$buf, [ref]$len)) {
  $state = [System.Runtime.InteropServices.Marshal]::ReadInt32($buf)
  [T]::WTSFreeMemory($buf)
  Write-Output ("session " + $sid + " connect state = " + $state + " (" + $names[$state] + ")")
} else { Write-Output "connect state query failed" }
$buf2 = [IntPtr]::Zero; $len2 = 0
if ([T]::WTSQuerySessionInformationW([IntPtr]::Zero, $sid, 6, [ref]$buf2, [ref]$len2)) {
  $win = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($buf2)
  [T]::WTSFreeMemory($buf2)
  Write-Output ("win station name       = " + $win)
} else { Write-Output "win station query failed" }
$buf3 = [IntPtr]::Zero; $len3 = 0
if ([T]::WTSQuerySessionInformationW([IntPtr]::Zero, $sid, 5, [ref]$buf3, [ref]$len3)) {
  $user = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($buf3)
  [T]::WTSFreeMemory($buf3)
  Write-Output ("session user           = " + $user)
}
Write-Output ("foreground window      = " + [T]::GetForegroundWindow())