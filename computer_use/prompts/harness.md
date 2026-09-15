# Computer Use harness (window2)

These function-calling tools map **1:1** to the official `sky` window2 API from `@oai/sky`.
Do not invent tools. Do not call `observe`, `wait`, `type`, or `keypress`.
Do not spawn `codex-computer-use.exe` or talk to the helper protocol; call the tools below.

Each tool name is the `sky` method name. Arguments are the official Input objects.

## Session state

Keep `apps`, `targetApp`, `targetWindow`, and `state` across turns, equivalent to `globalThis` in `node_repl`.
Never reconstruct a window from guessed fields. Use objects returned by `list_apps` / `list_windows` / `get_window` / `get_window_state`.

## Initialize (exactly one target window)

1. `list_apps`
2. Find the app by returned `id` / `displayName`
3. If `windows` is empty, `launch_app({app})` then `list_apps` again
4. Filter to exactly one window; if not exactly one, stop and report candidates
5. `get_window({id, app})`
6. `activate_window({window})`
7. `get_window_state({window})` (default: screenshot on, accessibility null)

## Two-cell act-and-refresh

Element indexes, screenshot IDs, and coordinates are valid only for the observation that produced them.

Accessibility path:

- Cell 1: `get_window_state({window, include_screenshot: false, include_text: true})` then stop and read `accessibility.tree`
- Cell 2: exactly one input (`click` with `element_index`, `set_value`, or `perform_secondary_action`), then `get_window_state({window, include_screenshot: true, include_text: true})`

Coordinate path:

- Cell 1: `get_window_state({window, include_screenshot: true, include_text: false})` then inspect screenshots
- Cell 2: exactly one input using `screenshotId` plus coordinates, then refresh

Typing:

- Cell 1: observe focus (`include_screenshot: true`, `include_text: true`) and read `accessibility.focused_element`
- Cell 2: `type_text({window, text})` then refresh. Use `press_key` for Return/Tab/arrows/Escape/chords.

`get_window_state({window})` defaults to screenshot + `accessibility: null`.
Request `include_text: true` only when you need indexes. Request both only when the next decision needs both.

Input methods return void. Refresh with a separate `get_window_state` call.

Follow `guidance.md` safety denies and `confirmations.md` before risky UI actions.

## Compression

Do not dump screenshot bytes back into the transcript. Default tool results omit `screenshot_base64` / data URLs and keep `screenshotId`. Call `emit_image: true` only when the next decision needs pixels. Prefer `include_text` XOR `include_screenshot`. Accessibility trees may be diffs; set `disableDiff` / `disableDiffing` for a full tree. Cap nodes/depth (1200/64).

## Cross-step state

Use `session_note` for internal reasoning to keep across steps. `session_state` returns handles, screenshot ids, and notes. Do not reconstruct windows.

## macOS window API

`get_app_state({app})`, `paste`, `select_text`. Clicks target `app` and **do not steal focus** unless `--steal-focus` / `steal_focus=true`. On Windows this maps to window2 without `activate_window`.

## Browser (separate plugin)

Prefer `tab_ax_write("state")` over DOM or screenshots. Batch AX actions then one `tab_ax_write`. `tab_dom_snapshot` / `tab_dom_click` are the dom_cua fallback. Coordinate `cua` clicks are last resort.

## Batch

`batch_actions({actions, then: "tab_ax_write"|"get_window_state"})` runs several mutations then one refresh.
