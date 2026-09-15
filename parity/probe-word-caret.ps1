# Expand the (degenerate) TextPattern selection to its enclosing paragraph/page/document
# and compare with the official's 454-char suffix, using numeric TextUnit constants because
# PowerShell resolves type literals at parse time (before Add-Type has run).
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$win = $null; foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and $n -match 'Word' -and $w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') { $win = $w } }
$docCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
$doc = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $docCond)
$holder = $null; [void]$doc.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$holder)
$sel = $holder.GetSelection()
Write-Output ('selection ranges=' + $sel.Count)
foreach ($unit in @(3, 4, 6)) {
  $r = $sel[0].Clone()
  $r.ExpandToEnclosingUnit($unit)
  $t = $r.GetText(-1)
  $head = if ($t.Length -gt 0) { $t.Substring(0, [Math]::Min(46, $t.Length)) -replace "`r", '<CR>' -replace "`n", '<LF>' } else { '<empty>' }
  Write-Output ('unit=' + $unit + ' len=' + $t.Length + ' head=[' + $head + ']')
}
Write-Output ('DEGENERATE? selection len=' + $sel[0].GetText(-1).Length)