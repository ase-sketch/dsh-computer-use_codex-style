# Raw UIA ground truth for the AX parity work: print Name / LocalizedControlType /
# AutomationId with whitespace made visible, so we can tell whether a difference is our
# trimming or the official's rewriting. Read-only: no input is sent to any window.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
function Vis([string]$s) {
  if ($null -eq $s) { return '<null>' }
  $out = ''
  foreach ($ch in $s.ToCharArray()) {
    $c = [int][char]$ch
    if ($c -eq 32) { $out += '~' }
    elseif ($c -eq 9) { $out += '\t' }
    elseif ($c -lt 32) { $out += ('<U+{0:X4}>' -f $c) }
    elseif ($c -gt 126) { $out += $ch }
    else { $out += $ch }
  }
  return $out
}
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$win = $null
foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and $n -match 'Word' -and $w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') { $win = $w; break } }
if (-not $win) { Write-Output 'NO WORD WINDOW'; exit 2 }
Write-Output ('WINDOW name=[' + (Vis $win.Current.Name) + '] lct=[' + (Vis $win.Current.LocalizedControlType) + '] ct=' + $win.Current.ControlType.ProgrammaticName)
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$script:hits = 0
function Walk($el, $depth) {
  if ($depth -gt 12 -or $script:hits -gt 60) { return }
  $name = $el.Current.Name; $lct = $el.Current.LocalizedControlType; $aid = $el.Current.AutomationId
  $interesting = ($aid -eq 'AutoSaveSwitch') -or ($el.Current.ControlType.ProgrammaticName -eq 'ControlType.TitleBar') -or ($aid -eq 'TabHome') -or ($aid -eq 'Undo')
  if ($interesting) {
    $script:hits++
    $sel = ''
    try { $p = $el.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern); $sel = 'hasSelectionItem isSelected=' + $p.Current.IsSelected } catch {}
    $enabled = $el.Current.IsEnabled
    Write-Output ('  d=' + $depth + ' aid=[' + (Vis $aid) + '] lct=[' + (Vis $lct) + '] nameLen=' + ($(if ($null -eq $name) { -1 } else { $name.Length })) + ' name=[' + (Vis $name) + '] enabled=' + $enabled + ' ' + $sel)
  }
  $c = $walker.GetFirstChild($el)
  while ($c) { Walk $c ($depth + 1); $c = $walker.GetNextSibling($c) }
}
Walk $win 0
Write-Output ('hits=' + $script:hits)