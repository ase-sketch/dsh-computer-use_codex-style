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
$form.Text = "DSH Parity Harness"
$form.Width = 540; $form.Height = 280
$form.StartPosition = "CenterScreen"
$label = New-Object System.Windows.Forms.Label
$label.Text = "Parity probe label"
$label.Left = 20; $label.Top = 20; $label.Width = 300
$text = New-Object System.Windows.Forms.TextBox
$text.Text = "parity-harness-initial"
$text.Left = 20; $text.Top = 52; $text.Width = 340
$text.Name = "ParityBox"
$button = New-Object System.Windows.Forms.Button
$button.Text = "Parity Button"
$button.Left = 20; $button.Top = 96; $button.Width = 150
$button.Name = "ParityButton"
$form.Controls.AddRange(@($label, $text, $button))
$form.Add_Shown({
  for ($i = 0; $i -lt 20; $i++) {
    [void][Fg]::Force($form.Handle)
    Start-Sleep -Milliseconds 250
    if ([Fg]::GetForegroundWindow() -eq $form.Handle) { Write-Output ("foreground acquired on attempt " + ($i + 1)); break }
  }
  if ([Fg]::GetForegroundWindow() -ne $form.Handle) { Write-Output "could not acquire foreground" }
})
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 120000
$timer.Add_Tick({ $timer.Stop(); $form.Close() })
$timer.Start()
[void]$form.ShowDialog()
Write-Output "harness window closed"