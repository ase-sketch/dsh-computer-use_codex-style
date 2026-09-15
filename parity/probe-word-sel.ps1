Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$win = $null; foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and $n -match 'Word' -and $w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') { $win = $w } }
$docCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
$doc = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $docCond)
$holder = $null; [void]$doc.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$holder)
$whole = $holder.DocumentRange.GetText(-1)
$sel = $holder.GetSelection()
Write-Output ('selection count=' + $sel.Count + ' len=' + $sel[0].GetText(-1).Length)
foreach ($unit in @(3,4,6)) { $r = $sel[0].Clone(); $r.ExpandToEnclosingUnit($unit); $t = $r.GetText(-1); Write-Output ('unit=' + $unit + ' len=' + $t.Length + ' head=[' + ($t.Substring(0,[Math]::Min(40,$t.Length)) -replace "`r",'<CR>' -replace "`n",'<LF>') + ']') }
$tail = $whole.Clone()
$tail.MoveEndpointByRange(0, $sel[0], 0)
$tt = $tail.GetText(-1)
Write-Output ('tailFromSelectionStart len=' + $tt.Length + ' head=[' + ($tt.Substring(0,[Math]::Min(40,$tt.Length)) -replace "`r",'<CR>') + ']')
