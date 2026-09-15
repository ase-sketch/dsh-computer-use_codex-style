# Which live patterns explain the official's `Secondary Actions: Raise`? The official shows
# Raise on the root window and on four Word panes, and on nothing else (no button, no tree
# item, no scroll bar). This probe counts live pattern availability per element so the
# predicate can be pinned instead of guessed.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$PATTERNS = @(
  @{ name = 'Invoke'; pat = [System.Windows.Automation.InvokePattern]::Pattern },
  @{ name = 'Window'; pat = [System.Windows.Automation.WindowPattern]::Pattern },
  @{ name = 'Scroll'; pat = [System.Windows.Automation.ScrollPattern]::Pattern },
  @{ name = 'ExpandCollapse'; pat = [System.Windows.Automation.ExpandCollapsePattern]::Pattern },
  @{ name = 'SelectionItem'; pat = [System.Windows.Automation.SelectionItemPattern]::Pattern },
  @{ name = 'Value'; pat = [System.Windows.Automation.ValuePattern]::Pattern },
  @{ name = 'RangeValue'; pat = [System.Windows.Automation.RangeValuePattern]::Pattern },
  @{ name = 'Toggle'; pat = [System.Windows.Automation.TogglePattern]::Pattern }
)
function Vis([string]$s) { if ($null -eq $s) { return '<null>' } else { return ($s -replace ' ', '~') } }
function PatternName($el) {
  $names = @()
  foreach ($p in $PATTERNS) {
    $holder = $null
    try { if ($el.TryGetCurrentPattern($p.pat, [ref]$holder)) { $names += $p.name } } catch {}
  }
  return ($names -join '+')
}
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$targets = @()
foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and ($n -match 'Word' -or $n -match 'Parity Target')) { $targets += $w } }
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
foreach ($win in $targets) {
  $script:winCounts = @{}; $script:raise = @(); $script:invoke = 0; $script:total = 0
  function Walk($el, $depth) {
    if ($depth -gt 12 -or $script:total -gt 900) { return }
    $script:total++
    $p = PatternName $el
    if ($p -match 'Window') { $script:raise += ('d=' + $depth + ' lct=[' + (Vis $el.Current.LocalizedControlType) + '] name=[' + (Vis $el.Current.Name) + '] aid=[' + (Vis $el.Current.AutomationId) + '] patterns=' + $p) }
    if ($p -match 'Invoke') { $script:invoke++ }
    if ($p -match 'Scroll') { $k = 'scroll+' + $p; $script:winCounts[$k] = 1 + $script:winCounts[$k] }
    if ($p -eq '') { $script:winCounts['none'] = 1 + $script:winCounts['none'] }
    $c = $walker.GetFirstChild($el)
    while ($c) { Walk $c ($depth + 1); $c = $walker.GetNextSibling($c) }
  }
  Walk $win 0
  Write-Output ('=== ' + (Vis $win.Current.Name) + ' visited=' + $script:total + ' invokeCapable=' + $script:invoke)
  Write-Output ('    WindowPattern elements (' + $script:raise.Count + '):')
  foreach ($r in $script:raise) { Write-Output ('      ' + $r) }
  $keys = $script:winCounts.Keys | Sort-Object
  foreach ($k in $keys) { Write-Output ('    ' + $k + ' x' + $script:winCounts[$k]) }
}
if (-not $targets.Count) { Write-Output 'no Word / Parity Target window found' }