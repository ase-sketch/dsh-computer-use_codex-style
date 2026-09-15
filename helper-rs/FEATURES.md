# Python → Rust helper inventory

Official helper EXE scope = window2 desktop (not IAB/CDP). Browser / mac AX / Chrome extension / audio stay Python sidecar.

## Python window2 surface (this binary)

| # | Feature | Python | helper-rs |
|---|---------|--------|-----------|
| 1 | Official JSONL `{id,method,params,meta}` + jsonrpc 2.0 | `rpc.py` | `protocol.rs` + `main.rs` |
| 2 | `call` envelope `{ok,name,value,images}` + detach data-URLs | `rpc.py` / `images.py` | `images.rs` |
| 3 | parent-pid watch | `rpc.py` | `main.rs` |
| 4 | WINDOW2 tools + JSON schema | `tools.py` | `tools.rs` |
| 5 | harness: batch / session_note / session_state / end_turn / diagnostic_state | `surfaces.py` `executor.py` | `main.rs` |
| 6 | aliases observe/type/keypress/window/click_element | `executor.py` | `main.rs` |
| 7 | health (dpi, WGC, ttl, allowedApps, observation, overlay) | `rpc.py` | `main.rs` |
| 8 | prompt markdown (window2 + confirmations, DSH branded) | `harness.py` `src/prompt.js` | `prompt.rs` |
| 9 | EnumWindows / list_apps / get_window / launch / activate | `win_enum.py` | `enum_windows.rs` |
| 10 | UserAssist useCount / lastUsedDate | `user_assist.py` | `assist.rs` |
| 11 | WGC FramePool JPEG CreateCopyFromSurfaceAsync + CPU crop | `wgc_winrt.py` `jpeg_winrt.py` | `capture.rs` |
| 12 | extra spaces menu/tooltip/popup + space identity | `win_capture.py` | `enum_windows.rs` |
| 13 | overlay exclude-from-capture | `overlay_win.py` | `overlay.rs` |
| 14 | UIA dump/cache/set_value/secondary/scroll | `win_uia.py` | `uia.rs` |
| 15 | UIA COM event sinks + WinEvent + invalidate | `win_uia.py` `_ComSink` | `uia.rs` |
| 16 | integrity-limited accessibility | `win_uia.py` | `uia.rs` |
| 17 | SendInput click/type/key/scroll/drag | `win_input.py` | `input.rs` |
| 18 | DPI PMv2 logical ↔ physical | `win_dpi.py` | `dpi.rs` |
| 19 | TTL lease 15s + window-id match | `freshness.py` | `state.rs` |
| 20 | human input monitor (injected ignored) | `input_monitor.py` | `interrupt.rs` |
| 21 | Esc LL hooks **only while overlay visible** | `interrupt.py` | `interrupt.rs` |
| 22 | terminal / Codex / AUMID / env allow-deny / Win-key | `policy.py` | `policy.rs` |
| 23 | approval gate `x-oai-cua-approved-app` | `approval.py` `rpc.py` | `main.rs` |
| 24 | notify_config analog under DSH_HOME | `notify_config.py` | `notify.rs` |
| 25 | turn-ended named events | `interrupt.py` | `interrupt.rs` |
| 26 | yellow Composition banner + WDA_EXCLUDEFROMCAPTURE | `overlay_win.py` `composition_overlay.py` | `overlay.rs` |
| 27 | software cursor HWND + Magic Move | `overlay_cursor.py` | `overlay.rs` |
| 28 | system cursor-manager **child** (never parent SetSystemCursor) | `cursor_manager.py` | `main.rs` / `overlay.rs` |
| 29 | set_value / scroll_element input fallback | `windows_backend.py` | `main.rs` |
| 30 | activate target window before input | API contract | `main.rs` |

## Stays Python (not official EXE)

- CDP / Playwright browser catalog, Chrome extension hub, native messaging
- mac AX: Swift helper `helper-swift/` (`sky.window` + AX/CGEvent). Official `bin-swift/*.exe` is Windows PE Swift, not Mach-O. Python `mac_api.py` remains a Windows mapping fallback.
- `audio_win.py` recording
- named-pipe NativePipeTransport (`pipe_server.py`) — DSH uses stdio
- fake backend, LLM loop, compact AX diff
- AV / password-manager policy tables (explicitly skipped)
- tools-surface: native `tools()` is window2/harness; DSH sidecar lazy-starts Python for `browser`/`mac`/`all` and non-window2 calls (`create_tab`, `tab_*`, `paste`)

## Remaining pass (after first 8)

- budget: `x-oai-cua-request-budget-ms` checked before/after dispatch (`computer-use request budget exhausted`)
- uia-id-space: official ID space exhausted string
- pipe: 4-byte LE named pipe (`SKY_CUA_NATIVE_PIPE`)

## Plan (this pass) — done

1. Policy + UserAssist + notify + interrupt + images + tools schema + prompt
2. Overlay Magic Move cursor HWND; arm/disarm Esc with visibility
3. UIA live COM sinks + WinEvent + cache invalidate; WindowOpened + event-cache TreeScope_Element gates monitor start
4. Wire approval, call envelope, space identity, health, fallbacks
5. `cargo build --release` + stdio smoke (health/tools/prompt/list_windows/list_apps/diagnostic eventMonitor/approval/launch_app/shutdown)
