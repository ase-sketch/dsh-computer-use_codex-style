# Compare the GUI-thread focus window of Word and Explorer against what the official
# helper reported as `focused_element` for each (Word: 56 编辑框 字体, Explorer: 208 编辑
# 地址栏 ID: TextBox) while neither window is foreground.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -Namespace DshGti2 -Name Native -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct GUITHREADINFO { public int cbSize; public int flags; public IntPtr hwndActive; public IntPtr hwndFocus; public IntPtr hwndCapture; public IntPtr hwndMenuOwner; public IntPtr hwndMoveSize; public IntPtr hwndCaret; public int rcCaretLeft; public int rcCaretTop; public int rcCaretRight; public int rcCaretBottom; }
[DllImport("user32.dll")] public static extern bool GetGUIThreadInfo(int idThread, ref GUITHREADINFO lpgui);
'@
function Vis([string]$s) { if ($null -eq $s) { return '<null>' } else { return ($s -replace ' ', '~') } }
foreach ($name in @('WINWORD', 'explorer')) {
  $procs = Get-Process -Name $name -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }
  foreach ($p in $procs) {
    Write-Output ('=== ' + $name + ' pid=' + $p.Id + ' mainHwnd=' + $p.MainWindowHandle)
    foreach ($t in $p.Threads) {
      $gti = New-Object DshGti2.Native+GUITHREADINFO
      $gti.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf([type]'DshGti2.Native+GUITHREADINFO')
      $ok = [DshGti2.Native]::GetGUIThreadInfo($t.Id, [ref]$gti)
      if ($ok -and ($gti.hwndFocus -ne [IntPtr]::Zero -or $gti.hwndActive -ne [IntPtr]::Zero)) {
        Write-Output ('  thread=' + $t.Id + ' active=' + $gti.hwndActive + ' focus=' + $gti.hwndFocus + ' caret=' + $gti.hwndCaret)
        if ($gti.hwndFocus -ne [IntPtr]::Zero) {
          try { $el = [System.Windows.Automation.AutomationElement]::FromHandle($gti.hwndFocus); if ($el) { Write-Output ('    FOCUSHWND lct=[' + (Vis $el.Current.LocalizedControlType) + '] name=[' + (Vis $el.Current.Name) + ']') } } catch { Write-Output ('    FromHandle failed') }
        }
      }
    }
  }
}