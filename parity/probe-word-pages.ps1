# The official's Word document_text is a 454-char suffix. Check the per-page elements: a
# 'page' TextPattern exposes only that page's text.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$win = $null; foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and $n -match 'Word' -and $w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') { $win = $w } }
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Pane)
$panes = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$TEXTPAT = [System.Windows.Automation.TextPattern]::Pattern
Write-Output ('panes=' + $panes.Count)
foreach ($p in $panes) {
  $holder = $null
  if (-not $p.TryGetCurrentPattern($TEXTPAT, [ref]$holder)) { continue }
  $t = $holder.DocumentRange.GetText(-1)
  $head = if ($t.Length -gt 0) { $t.Substring(0, [Math]::Min(30, $t.Length)) -replace "`r", '<CR>' -replace "`n", '<LF>' } else { '<empty>' }
  Write-Output ('  lct=[' + $p.Current.LocalizedControlType + '] name=[' + ($p.Current.Name -replace ' ', '~') + '] docLen=' + $t.Length + ' head=[' + $head + ']')
}