# The official reports a focused element for a background window (Word: 56 编辑框 字体,
# Explorer: 208 编辑 地址栏 ID: TextBox) while UIA's HasKeyboardFocus is false everywhere.
# Hypothesis: it reads MSAA's focused state through LegacyIAccessiblePattern
# (STATE_SYSTEM_FOCUSED = 0x4), which the providers keep for the window's last focused
# control.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$LEG = [System.Windows.Automation.LegacyIAccessiblePattern]::Pattern
function Vis([string]$s) { if ($null -eq $s) { return '<null>' } else { return ($s -replace ' ', '~') } }
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
foreach ($w in $wins) {
  $n = $w.Current.Name; if (-not $n) { continue }
  if (-not ($n -match 'Word' -or $n -match '文件资源管理器' -or $n -match 'Temp')) { continue }
  if ($w.Current.ControlType.ProgrammaticName -ne 'ControlType.Window') { continue }
  $script:hits = @(); $script:n = 0; $script:legacy = 0
  function Walk($el, $depth) {
    if ($depth -gt 12 -or $script:n -gt 900) { return }
    $script:n++
    $holder = $null
    if ($el.TryGetCurrentPattern($LEG, [ref]$holder)) {
      $script:legacy++
      try { $st = $holder.Current.State; if (($st -band 4) -ne 0) { $script:hits += ('lct=[' + (Vis $el.Current.LocalizedControlType) + '] name=[' + (Vis $el.Current.Name) + '] aid=[' + (Vis $el.Current.AutomationId) + '] state=0x' + ('{0:X}' -f $st)) } } catch {}
    }
    $c = $walker.GetFirstChild($el)
    while ($c) { Walk $c ($depth + 1); $c = $walker.GetNextSibling($c) }
  }
  Walk $w 0
  Write-Output ('=== [' + (Vis $n) + '] visited=' + $script:n + ' legacyCapable=' + $script:legacy + ' MSAA-focused-hits=' + $script:hits.Count)
  foreach ($h in $script:hits) { Write-Output ('    ' + $h) }
}