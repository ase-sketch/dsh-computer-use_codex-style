# The official's Word `document_text` is 454 chars starting mid-document while
# TextPattern.DocumentRange is the whole 4732-char body. Hypothesis: the official uses the
# provider's *visible* ranges (what is on screen), not the document range.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$win = $null; foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and $n -match 'Word' -and $w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') { $win = $w } }
if (-not $win) { Write-Output 'no Word window'; exit 2 }
$docCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
$doc = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $docCond)
if (-not $doc) { Write-Output 'no document element'; exit 3 }
Write-Output ('document name=[' + $doc.Current.Name + ']')
$holder = $null
if (-not $doc.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$holder)) { Write-Output 'no TextPattern'; exit 4 }
$whole = $holder.DocumentRange.GetText(-1)
Write-Output ('DocumentRange len=' + $whole.Length)
$vis = $holder.GetVisibleRanges()
Write-Output ('visible ranges=' + $vis.Count)
$total = 0
for ($i = 0; $i -lt $vis.Count; $i++) { $t = $vis[$i].GetText(-1); $total += $t.Length; Write-Output ('  range ' + $i + ' len=' + $t.Length + ' start=[' + ($t.Substring(0, [Math]::Min(50, $t.Length)) -replace "`r", '<CR>' -replace "`n", '<LF>') + ']') }
Write-Output ('visible total=' + $total)
$sel = $holder.GetSelection()
if ($sel -and $sel.Count -gt 0) { $st = $sel[0].GetText(-1); Write-Output ('selection len=' + $st.Length + ' start=[' + ($st.Substring(0, [Math]::Min(50, $st.Length)) -replace "`r", '<CR>' -replace "`n", '<LF>') + ']') } else { Write-Output 'selection empty' }
Write-Output ('doc text ends with: [' + ($whole.Substring([Math]::Max(0, $whole.Length - 60)) -replace "`r", '<CR>') + ']')