# Derived paths only: no machine-specific absolute path belongs in a tracked script.
#   $RepoRoot   the repository (this script lives in parity/)
#   $DshHome    DSH_HOME, else USERPROFILE/.dsh
#   $CodexHome  CODEX_HOME, else USERPROFILE/.codex
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$ErrorActionPreference = "Stop"
# The mirror is a local convenience: it copies the human-facing documents plus a source
# snapshot elsewhere on this machine. Point CU_MIRROR_DIR at it; the default is a sibling
# directory of this repository.
$mirrorTarget = if ($env:CU_MIRROR_DIR) { $env:CU_MIRROR_DIR } else { Join-Path (Split-Path -Parent $RepoRoot) 'cua-parity' }
$dest = Join-Path $mirrorTarget 'code'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$root = "$RepoRoot"
$map = [ordered]@{
  "helper-rs\src\overlay\motion.rs"           = "helper-motion.rs"
  "helper-rs\src\overlay\mod.rs"              = "helper-overlay-mod.rs"
  "helper-rs\src\interrupt.rs"                = "helper-interrupt.rs"
  "helper-rs\src\tools.rs"                    = "helper-tools.rs"
  "helper-rs\src\uia.rs"                      = "helper-uia.rs"
  "helper-rs\src\policy.rs"                   = "helper-policy.rs"
  "helper-rs\src\protocol.rs"                 = "helper-protocol.rs"
  "helper-rs\src\prompt.rs"                   = "helper-prompt.rs"
  "helper-rs\src\state.rs"                    = "helper-state.rs"
  "helper-rs\src\main.rs"                     = "helper-main.rs"
  "helper-rs\src\desktop.rs"                  = "helper-desktop.rs"
  "helper-rs\src\notify.rs"                   = "helper-notify.rs"
  "helper-rs\src\app_catalog.rs"              = "helper-app_catalog.rs"
  "helper-rs\assets\prompts\dsh-header.md"    = "prompt-dsh-header.md"
  "helper-rs\assets\prompts\guidance.md"      = "prompt-guidance.md"
  "helper-rs\assets\prompts\api.md"           = "prompt-api.md"
  "helper-rs\assets\prompts\confirmations.md" = "prompt-confirmations.md"
  "src\sidecar.js"                 = "plugin-sidecar.js"
  "src\prompt.js"                  = "plugin-prompt.js"
  "src\tool.js"                    = "plugin-tool.js"
  "src\index.js"                   = "plugin-index.js"
  "cordis.patch.yml"                = "plugin-cordis.patch.yml"
  "skills\computer-use\SKILL.md"   = "skill-computer-use.md"
  "computer_use\browser_schemas.py"            = "py-browser_schemas.py"
  "computer_use\browser_security.py"           = "py-browser_security.py"
  "computer_use\browser_official.py"           = "py-browser_official.py"
  "computer_use\policy.py"                     = "py-policy.py"
  "computer_use\rpc.py"                        = "py-rpc.py"
  "parity\CHECKLIST.md"                        = "CHECKLIST.md"
  "parity\smoke-axdiff.mjs"                    = "smoke-axdiff.mjs"
  "parity\check_browser.py"                    = "check_browser.py"
  "parity\check_security.py"                   = "check_security.py"
  "helper-rs\src\capture.rs"                  = "helper-capture.rs"
  "parity\verify-all.ps1"                      = "verify-all.ps1"
  "parity\cursor-trace.mjs"                    = "cursor-trace.mjs"
  "parity\fresh-test.mjs"                      = "fresh-test.mjs"
  "parity\fresh-diff.ps1"                      = "fresh-diff.ps1"
  "parity\lag-scan.ps1"                        = "lag-scan.ps1"
  "parity\pill-probe.mjs"                      = "pill-probe.mjs"
  "parity\pill-probe.ps1"                      = "pill-probe.ps1"
  "parity\pill-crop.ps1"                       = "pill-crop.ps1"
  "parity\dcomp-selftest.mjs"                  = "dcomp-selftest.mjs"
  "parity\screen-shot.ps1"                     = "screen-shot.ps1"
  "helper-rs\src\input.rs"                    = "helper-input.rs"
  "helper-rs\src\enum_windows.rs"             = "helper-enum_windows.rs"
  "parity\interactive-physical.mjs"            = "interactive-physical.mjs"
  "parity\inject-click.ps1"                    = "inject-click.ps1"
  "parity\inject-key.ps1"                      = "inject-key.ps1"
  "parity\raise-target.ps1"                    = "raise-target.ps1"
  "parity\golden-ax.mjs"                       = "golden-ax.mjs"
  "parity\window-states.mjs"                   = "window-states.mjs"
  "parity\window-state.ps1"                    = "window-state.ps1"
  "parity\occlude-target.ps1"                  = "occlude-target.ps1"
  "parity\overlay-lifecycle.mjs"               = "overlay-lifecycle.mjs"
  "parity\plugin-lifecycle.mjs"                = "plugin-lifecycle.mjs"
  "parity\overlay-lifecycle.json"              = "evidence-overlay-lifecycle.json"
  "parity\overlay-probe.ps1"                   = "overlay-probe.ps1"
  "parity\cursor-suppression.ps1"              = "cursor-suppression.ps1"
  "parity\restore-cursors.ps1"                 = "restore-cursors.ps1"
  "parity\golden-ax\official.tree.txt"         = "evidence-official-ax-tree.txt"
  "parity\pill-visible.png"                    = "evidence-pill-visible.png"
  "parity\pill-exact.png"                      = "evidence-pill-crop.png"
  "parity\lag-a.jpg"                           = "evidence-cursor-in-shot.jpg"
  "parity\cursor-trace.jpg"                    = "evidence-cursor-first-shot.jpg"
  # Wave 3 additions: the AX A/B + interrupt-marker gates, the single-source constant file,
  # the new helper/plugin modules and the browser gates the Wave-3 agents added.
  "helper-rs\src\policy\url_policy.rs"       = "helper-url_policy.rs"
  "helper-rs\src\audio.rs"                   = "helper-audio.rs"
  "helper-rs\src\images.rs"                  = "helper-images.rs"
  "parity\check-claims.ps1"                   = "check-claims.ps1"
  "parity\ax-rich-parity.mjs"                 = "ax-rich-parity.mjs"
  "parity\interrupt-marker.mjs"               = "interrupt-marker.mjs"
  "parity\restore-window.ps1"                 = "restore-window.ps1"
  "parity\motion-curve.mjs"                   = "motion-curve.mjs"
  "parity\official-constants.json"            = "official-constants.json"
  "parity\claim-prompt-budget.mjs"            = "claim-prompt-budget.mjs"
  "parity\check_browser_url_gate.py"          = "check_browser_url_gate.py"
  "parity\check_browser_persistence.py"       = "check_browser_persistence.py"
  "parity\check_browser_transport.py"         = "check_browser_transport.py"
  "parity\check_browser_notifications.py"     = "check_browser_notifications.py"
  "computer_use\tree_format.py"               = "py-tree_format.py"
  "computer_use\browser_persistence.py"       = "py-browser_persistence.py"
  "computer_use\extension_transport.py"       = "py-extension_transport.py"
  "parity\ax-rich\word.official.txt"         = "evidence-ax-word-official.txt"
  "parity\ax-rich\word.ours.txt"             = "evidence-ax-word-ours.txt"
  "parity\\sidecar-observe-act.mjs"          = "sidecar-observe-act.mjs"
}
$missing = @()
$count = 0
foreach ($k in $map.Keys) {
  $src = Join-Path $root $k
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $dest $map[$k]) -Force
    $count++
  } else { $missing += $k }
}
Write-Output ("copied: " + $count)
if ($missing.Count) { Write-Output ("missing: " + ($missing -join ", ")) }
# The mirror keeps the human-facing documents at its root, next to `code/` rather than
# inside it: the plan, the acceptance checklist, and the status README (README is
# authored in the mirror and is deliberately not overwritten from here).
$mirror = $mirrorTarget
$rootDocs = [ordered]@{
  'analysis\dsh-computer-use-parity-plan.md' = 'DSH-ComputerUse-官方对齐实施计划.md'
  'parity\CHECKLIST.md'                      = 'CHECKLIST.md'
}
# Deep-dive 调研（第 15 轮）：9 份子代理报告 + 合并登记册 + 核验日志，整体进 `deep-dive/`。
$dd = Join-Path $mirror 'deep-dive'
New-Item -ItemType Directory -Force -Path $dd | Out-Null
$ddCount = 0
foreach ($f in (Get-ChildItem (Join-Path $root 'analysis\deep-dive') -File -Filter '*.md' -ErrorAction SilentlyContinue)) {
  Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $dd $f.Name) -Force
  $ddCount++
}
Write-Output ('deep-dive: ' + $ddCount + ' files')

foreach ($k in $rootDocs.Keys) {
  $src = Join-Path $root $k
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $mirror $rootDocs[$k]) -Force
    Write-Output ('root: ' + $rootDocs[$k])
  } else { Write-Output ('root missing: ' + $k) }
}
Get-ChildItem -File $dest | Select-Object Name, @{n="KB";e={[math]::Round($_.Length/1024,1)}} | Sort-Object Name | Format-Table -AutoSize | Out-String -Width 150