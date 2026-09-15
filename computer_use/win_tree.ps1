param(
    [Parameter(Mandatory = $true)][Int64]$Hwnd,
    [int]$Max = 250
)

Add-Type -TypeDefinition @"
using System.Runtime.InteropServices;
public static class NativeDpi {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(System.IntPtr value);
}
"@
[void][NativeDpi]::SetProcessDpiAwarenessContext([IntPtr]-4)

Add-Type -AssemblyName UIAutomationClient
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
if ($null -eq $root) {
    Write-Output "[]"
    exit 0
}

$nodes = New-Object System.Collections.Generic.List[object]
$index = 0
$trueCondition = [System.Windows.Automation.Condition]::TrueCondition
$childScope = [System.Windows.Automation.TreeScope]::Children

function Walk($element, [int]$depth) {
    if ($script:nodes.Count -ge $Max) { return }
    $rect = $element.Current.BoundingRectangle
    $role = [string]$element.Current.LocalizedControlType
    if ([string]::IsNullOrWhiteSpace($role)) {
        $role = [string]$element.Current.ControlType.ProgrammaticName
        $role = $role -replace '^ControlType\.', ''
    }
    $script:nodes.Add([pscustomobject]@{
            index  = $script:index
            role   = $role
            name   = [string]$element.Current.Name
            x      = [double]$rect.X
            y      = [double]$rect.Y
            width  = [double]$rect.Width
            height = [double]$rect.Height
            depth  = $depth
            value  = [string]$element.Current.Name
        })
    $script:index++
    foreach ($child in $element.FindAll($childScope, $trueCondition)) {
        Walk $child ($depth + 1)
    }
}

Walk $root 0
$script:nodes | ConvertTo-Json -Compress -Depth 4
