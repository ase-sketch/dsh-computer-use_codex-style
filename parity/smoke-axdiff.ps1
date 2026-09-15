# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Continue"
$exe = "$RepoRoot\helper-rs\target\release\dsh-computer-use.exe"
$out = '{"id":1,"method":"list_windows","params":{}}' | & $exe --parent-pid 0 2>$null
$obj = $out | ConvertFrom-Json
$target = @($obj.result | Where-Object { $_.app -eq "explorer.exe" -and $_.title -ne "" })[0]
if ($null -eq $target) { $target = @($obj.result | Where-Object { $_.title -ne "" })[0] }
Write-Output ("target app=" + $target.app + " id=" + $target.id + " title=" + $target.title)
$win = '{"app":"' + $target.app + '","id":' + $target.id + '}'
$reqs = @(
  ('{"id":2,"method":"get_window_state","params":{"window":' + $win + ',"include_screenshot":false,"include_text":true}}'),
  ('{"id":3,"method":"get_window_state","params":{"window":' + $win + ',"include_screenshot":false,"include_text":true}}'),
  ('{"id":4,"method":"get_window_state","params":{"window":' + $win + ',"include_screenshot":false,"include_text":true,"disableDiffing":true}}'),
  ('{"id":5,"method":"get_window_state","params":{"window":' + $win + ',"include_screenshot":true,"include_text":false}}'),
  ('{"id":6,"method":"get_window_state","params":{"window":' + $win + ',"include_screenshot":false,"include_text":true}}')
)
$out2 = $reqs | & $exe --parent-pid 0 2>$null
$objs = @($out2 | ForEach-Object { $_ | ConvertFrom-Json })
foreach ($o in $objs) {
  if ($o.id -eq 1) { continue }
  if ($o.ok -ne $true) { Write-Output ("call " + $o.id + " ERROR: " + $o.error); continue }
  $acc = $o.result.accessibility
  $n = if ($o.result.screenshots) { @($o.result.screenshots).Count } else { 0 }
  if ($null -eq $acc) { Write-Output ("call " + $o.id + " : accessibility=null shots=" + $n); continue }
  $t = [string]$acc.tree
  Write-Output ("call " + $o.id + " : diff=" + $acc.diff + " len=" + $t.Length + " shots=" + $n)
  $head = $t.Substring(0, [Math]::Min(260, $t.Length))
  Write-Output ("   " + ($head -replace "`r?`n", " / "))
}