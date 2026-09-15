# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition ([System.IO.File]::ReadAllText("$RepoRoot\parity\Fg.cs.txt"))
$form = New-Object System.Windows.Forms.Form
$form.Text = "Parity Target"
$form.Width = 640; $form.Height = 420
$form.StartPosition = "Manual"
$form.Left = 220; $form.Top = 160
$label = New-Object System.Windows.Forms.Label
$label.Text = "Parity probe label"
$label.Left = 24; $label.Top = 24; $label.Width = 300; $label.Height = 24
$text = New-Object System.Windows.Forms.TextBox
$text.Text = "parity-initial"
$text.Left = 24; $text.Top = 60; $text.Width = 360; $text.Height = 28
$text.Name = "ParityBox"
$button = New-Object System.Windows.Forms.Button
$button.Text = "Parity Button"
$button.Left = 24; $button.Top = 110; $button.Width = 160; $button.Height = 34
$button.Name = "ParityButton"
$form.Controls.AddRange(@($label, $text, $button))
$form.Add_Shown({
  for ($i = 0; $i -lt 20; $i++) {
    [void][Fg]::Force($form.Handle)
    Start-Sleep -Milliseconds 250
    if ([Fg]::GetForegroundWindow() -eq $form.Handle) { break }
  }
})
# Record the button center in screen coordinates so the test can click it.
$btnTimer = New-Object System.Windows.Forms.Timer
$btnTimer.Interval = 1500
$btnTimer.Add_Tick({
  $btnTimer.Stop()
  $p = $button.PointToScreen((New-Object System.Drawing.Point([int]($button.Width/2), [int]($button.Height/2))))
  Set-Content -Path "$RepoRoot\parity\target-geometry.json" -Value (("{""hwnd"":{0},""screenX"":{1},""screenY"":{2},""formX"":{3},""formY"":{4},""clientX"":{5},""clientY"":{6}}" -f $form.Handle, $p.X, $p.Y, $form.Left, $form.Top, ($p.X - $form.Left - 8), ($p.Y - $form.Top - 31)))
  Write-Output ("geometry written: screen=" + $p.X + "," + $p.Y)
})
$btnTimer.Start()
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 900000
$timer.Add_Tick({ $timer.Stop(); $form.Close() })
$timer.Start()
[void]$form.ShowDialog()
Write-Output "target window closed"