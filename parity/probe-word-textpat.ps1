# Which element's TextPattern yields the official's 454-char suffix? Walk Word and print
# every TextPattern-capable element's DocumentRange length and head.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$win = $null; foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and $n -match 'Word' -and $w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') { $win = $w } }
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$TEXTPAT = [System.Windows.Automation.TextPattern]::Pattern
$script:n = 0
function Walk($el, $depth) {
  if ($depth -gt 14 -or $script:n -gt 900) { return }
  $script:n++
  $holder = $null
  try {
    if ($el.TryGetCurrentPattern($TEXTPAT, [ref]$holder)) {
      $len = -1; $head = ''
      try { $t = $holder.DocumentRange.GetText(-1); $len = $t.Length; $head = $t.Substring(0, [Math]::Min(28, $t.Length)) -replace "`r", '<CR>' -replace "`n", '<LF>' } catch {}
      $vis = $holder.GetVisibleRanges(); $vlen = 0
      for ($i = 0; $i -lt $vis.Count; $i++) { $vlen += $vis[$i].GetText(-1).Length }
      Write-Output ('TEXTPAT depth=' + $depth + ' lct=[' + $el.Current.LocalizedControlType + '] name=[' + ($el.Current.Name -replace ' ', '~') + '] docLen=' + $len + ' visibleLen=' + $vlen + ' head=[' + $head + ']')
    }
  } catch {}
  $c = $walker.GetFirstChild($el)
  while ($c) { Walk $c ($depth + 1); $c = $walker.GetNextSibling($c) }
}
Walk $win 0
Write-Output ('visited=' + $script:n)