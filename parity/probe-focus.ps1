# Focus ground truth for the AX parity work: who does the system say is focused, is Word
# foreground, and which Word elements report keyboard focus?
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -Namespace DshFg -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder t, int n);
'@
function Vis([string]$s) { if ($null -eq $s) { return '<null>' } else { return ($s -replace ' ', '~') } }
$fg = [DshFg.Native]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 512
[void][DshFg.Native]::GetWindowText($fg, $sb, 512)
Write-Output ('foreground=[' + (Vis $sb.ToString()) + '] hwnd=' + $fg)
$auto = [System.Windows.Automation.AutomationElement]
$fe = $auto::FocusedElement
if ($fe) { Write-Output ('FocusedElement lct=[' + (Vis $fe.Current.LocalizedControlType) + '] name=[' + (Vis $fe.Current.Name) + '] aid=[' + (Vis $fe.Current.AutomationId) + '] hasFocus=' + $fe.Current.HasKeyboardFocus) } else { Write-Output 'FocusedElement=null' }
$root = $auto::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$win = $null; foreach ($w in $wins) { $n = $w.Current.Name; if ($n -and $n -match 'Word' -and $w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') { $win = $w } }
if ($win) {
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $script:focusHits = @(); $script:n = 0
  function Walk($el, $depth) {
    if ($depth -gt 12 -or $script:n -gt 900) { return }
    $script:n++
    if ($el.Current.HasKeyboardFocus) { $script:focusHits += ('lct=[' + (Vis $el.Current.LocalizedControlType) + '] name=[' + (Vis $el.Current.Name) + '] aid=[' + (Vis $el.Current.AutomationId) + ']') }
    $c = $walker.GetFirstChild($el)
    while ($c) { Walk $c ($depth + 1); $c = $walker.GetNextSibling($c) }
  }
  Walk $win 0
  Write-Output ('visited=' + $script:n + ' hasKeyboardFocusHits=' + $script:focusHits.Count)
  foreach ($h in $script:focusHits) { Write-Output ('  FOCUS ' + $h) }
}