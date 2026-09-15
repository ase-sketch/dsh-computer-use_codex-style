# Recovered Codex Computer Use protocol (Windows)

Read from the local install, not copied as a runtime:

- `~/.codex/plugins/cache/openai-bundled/computer-use/*/docs/api.md`
- `@oai/sky` `WindowsComputerUseClientBase` / `WindowsHelperTransport`
- `codex-computer-use.exe` method table and accessibility strings

## Transports

Stdio helper: one JSON object per line `{id, method, params, meta?}`.
Native pipe (`SKY_CUA_NATIVE_PIPE=1`): 4-byte little-endian length + JSON-RPC `{jsonrpc:"2.0", method:"request", params:{method, params}}`.

## Observe payload

`get_window_state` returns:

- `window`: `{app, id, title?}`
- `screenshots[]`: `{id, url (data URL), zIndex, originX?, originY?, width?, height?}`
- `accessibility`: `{tree, focused_element?, selected_text?, selected_elements?, document_text?}` or null

Tree text is prefixed with `Window: "<title>", App: ...` and includes element indexes. This driver also exposes structured nodes `{index, role, name, bounds}`.

## Action verbs

`click` (coords) / `click_element` (index), `type_text`, `press_key`, `scroll`, `drag`, `set_value`, `perform_secondary_action`, `activate_window`, `launch_app`.
