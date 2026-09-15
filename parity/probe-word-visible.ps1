Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$win = $null; foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and $n -match 'Word' -and $w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') { $win = $w } }
$docCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
$doc = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $docCond)
$holder = $null; [void]$doc.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$holder)
$vis = $holder.GetVisibleRanges()
$parts = @(); for ($i = 0; $i -lt $vis.Count; $i++) { $parts += $vis[$i].GetText(-1) }
$joined = ($parts -join "`n") -replace "`r`n", "`n" -replace "`r", "`n"
Write-Output ('visibleRanges=' + $vis.Count + ' joinedLen=' + $joined.Length)
Write-Output ('joinedHead=[' + ($joined.Substring(0, [Math]::Min(46, $joined.Length)) -replace "`n", '<LF>') + ']')
