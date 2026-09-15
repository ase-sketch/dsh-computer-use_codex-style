# Recovered helper behavior (readable, not original Rust)

Source: local `codex-computer-use.exe` strings + `@oai/sky` Windows client.

## Process

Spawn `codex-computer-use.exe --parent-pid <pid>`. Stdio JSON lines:

```
{"id":1,"method":"list_apps","params":{},"meta":{...}}
{"id":1,"ok":true,"result":[...]}
```

Named-pipe mode: 4-byte LE length + JSON-RPC `{method:"request", params:{method, params}}`.

## Modules (from panic paths)

`src/accessibility.rs`, `accessibility/monitor.rs`, `capture/image.rs`, `dpi.rs`, `input/initial_cursor.rs`, `input/interruption.rs`, `overlay/*`, `shell/app_catalog.rs`, `policy/*`, `app.rs`.

## Observe

`GetWindowStateParams { window, include_screenshot, include_text }`.

Must request screenshot, text, or both.

Screenshots: WGC (`IGraphicsCaptureItemInterop`, `Direct3D11CaptureFramePool`, JPEG encoder). Fields: `id, zIndex, url, originX, originY, width, height`.

Accessibility: UIA snapshot + event cache. Fields: `tree, focused_element, selected_text, selected_elements, document_text`. Indexes map to cached `bounds`. Prefixes: `Window: "…", App: …`, `The focused UI element is`, `Document text: ```…````.

Window identity: `app, id, title` plus internal `appId, processId, rootHwnd, inputHwnd, processName, snapshotRevision`.

## Input

- Indexed click → helper method `click_element` (UIA cached bounds). Missing cache: `has no cached bounds`.
- Coordinate click/scroll/drag → window-relative, rounded; optional `screenshotId` must be in cache (`unknown screenshotId`). Outside viewport / window bounds is rejected. Hit-test must stay on target window (`not target window`; activate or retake screenshot).
- `click_count >= 1`. `right double click is not supported`.
- `set_value` / `perform_secondary_action` use element index. Secondary labels: Raise, Scroll Up/Down/Left/Right, Expand, Collapse (case-insensitive). Scroll/ExpandCollapse fail if the UIA pattern disappeared.
- Keys: X11-style chords with aliases (`Control`/`CTRL_L`/`Control_L`, `KP_Enter`/`Numpad_Enter`, `period`/`greater`, …).
- Minimized: `window is minimized; call activate_window, refresh with get_window_state`.
- Physical Escape / user input in the target window invalidates the snapshot.

## Overlay / interrupt / catalog / approval

- Overlay class `CodexComputerUseCursorOverlay`, banner `Codex is using your computer` + `Esc to cancel`.
- Physical Escape writes `cache/computer-use/interrupts/{session}/{turn}` and aborts the turn.
- Turn end: helper method `end_turn`, named event `Local\CodexComputerUseTurnEnded-{session}`, meta `x-codex-turn-metadata` (`session_id`/`turn_id`).
- Indexed scroll uses helper `scroll_element` (4-field ElementScrollParams); coordinate scroll stays `scroll`.
- After accept, retries the original method with `x-oai-cua-approved-app`.
- `WH_MOUSE_LL` watches overlay input; reconstructed driver also hooks Escape.
- App catalog reads `HKCU\...\Explorer\UserAssist\*\Count` (ROT13 names) → `lastUsedDate` / `useCount`.
- `AppApprovalRequest {app, displayName, riskLevel, allowPersistentApproval}` then JS elicitation (`session` / `always`).
- WGC: `CreateForMonitor`, crop window out of the monitor frame, `SetIsCursorCaptureEnabled(false)`, `SetIsBorderRequired(false)`, JPEG encode. Pixel fallback: PrintWindow `PW_RENDERFULLCONTENT`.
