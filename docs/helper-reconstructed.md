# Reconstructed helper source map

Not OpenAI's original Rust tree. This is a module-by-module reconstruction of
`codex-computer-use.exe` (1.5MB, stripped) plus `@oai/sky` Windows client.

| Helper path | Recovered behavior | Driver module |
|-------------|--------------------|---------------|
| src/app.rs | JSON-line `{id,method,params,meta}` dispatch | `computer_use/executor.py` |
| src/accessibility.rs + monitor.rs | UIA snapshot, cached bounds, focused/selected text | `win_tree.py` |
| src/capture/image.rs | WGC CreateForMonitor, crop window, JPEG, no cursor/border | `wgc.py`, `win_capture.py` |
| src/overlay/* | CodexComputerUseCursorOverlay, banner, Esc to cancel | `overlay.py` |
| src/input/interruption.rs | physical Escape, keyboard+mouse hooks, turn-ended named event | `interrupt.py`, `turn.py` |
| src/shell/app_catalog.rs | UserAssist `\Count`, last_used, use_count | `user_assist.py` |
| AppApprovalRequest | riskLevel, allowPersistentApproval, elicitation | `approval.py` |
| src/policy/* | LockApp, URL policy, terminal/Codex deny | `policy.py` |

Live pixels still fall back to PrintWindow(PW_RENDERFULLCONTENT) when a D3D
capture device is missing; crop/session flags match the helper anyway.
