# helper-linux — DSH Computer Use, Linux backend

`dsh-computer-use` is the Linux desktop driver for the `dsh-computer-use` plugin. It is a
**fork** of [`ilysenko/codex-desktop-linux`](https://github.com/ilysenko/codex-desktop-linux)
(MIT), specifically its `computer-use-linux` crate, re-pointed at this plugin's stdio JSONL
helper protocol. The desktop backends — AT-SPI accessibility, XDG Desktop Portal screenshot
and input, and the per-compositor window backends (KWin, GNOME Shell, Hyprland, Niri, i3,
COSMIC, X11) — are upstream code and are kept as close to upstream as the protocol change
allows.

```
fork source   https://github.com/ilysenko/codex-desktop-linux
upstream crate computer-use-linux 0.4.9-linux-alpha1
upstream commit 5f7310d71dd02e6e0131deec6fa89d26c8bcaf9c
license        MIT (see LICENSE, copied from the upstream repository)
```

## Layout

| path | what it is |
| --- | --- |
| `src/protocol.rs` | the JSONL request/response envelope, and the split of a screenshot into its own image part |
| `src/helper.rs` | the dispatcher: `health` / `tools` / `call` / `interrupt` / `shutdown` / `prompt` / `end_turn`, and the seven-tool surface |
| `src/server.rs` | upstream MCP server, unchanged in its handlers; the fork only adds the two hooks the dispatcher drives |
| `src/main.rs` | entry point: no arguments (or `helper`) speaks JSONL, `mcp` keeps the original MCP server, the rest are upstream diagnostics subcommands |
| `scripts/smoke-jsonl.sh` | protocol-level smoke test; `scripts/smoke_assert.py` holds its assertions |
| `gnome-shell-extension/` | upstream optional window-targeting extension |

## Build

```sh
cargo build --release            # -> target/release/dsh-computer-use
cargo test                       # upstream suite plus the protocol tests
bash scripts/smoke-jsonl.sh      # drives the built binary over a pipe
```

## Protocol

One JSON object per line in, one per line out.

```json
-> {"id":1,"method":"call","params":{"name":"list_apps","arguments":{}},"meta":{"x-oai-cua-request-budget-ms":15000}}
<- {"id":1,"ok":true,"result":{"ok":true,"name":"list_apps","value":{...},"images":[]}}
```

Methods: `health`, `tools`, `call`, `interrupt`, `shutdown`, `prompt`, `end_turn`.

- `health` reports what the helper is and what actually works **on this machine**, taken from
  the crate's own diagnostics probes. Failed checks are listed verbatim under `degraded`;
  nothing is reported as working that did not prove it.
- `tools` lists exactly the seven exposed tools, with the crate's own JSON Schemas.
- `call` returns `{ok, name, value, images}`. Screenshot pixels are never inlined into `value`:
  each image becomes its own part as `{mimeType, data, name}` with the `data:` URL prefix
  stripped, and the caption stays in `value`.
- `interrupt` stops the call in progress (not merely the next one) and latches the helper
  stopped until `end_turn` clears it.
- `end_turn` is safe to call repeatedly and never strands the helper: the host reuses one
  process across turns.
- `shutdown` is terminal; calls the host already sent are answered as abandoned rather than
  run to completion.

Unknown methods and unadvertised tools are both refused as `unsupported method: <name>`, which
is the upstream helper's own wording.

## Tool surface

Exactly seven tools, under their upstream Linux names and parameter shapes:
`list_apps`, `get_app_state`, `screenshot`, `click`, `scroll`, `press_key`, `type_text`.

The crate advertises more tools over MCP (`doctor`, `setup_accessibility`,
`setup_window_targeting`, `list_windows`, `focused_window`, `activate_window`,
`perform_action`, `set_value`, `drag`, `move_window`, `resize_window`). They are neither listed
by `tools` nor routable through `call`.

`get_app_state` accepts `app_name_or_bundle_identifier` as well as the window selectors
(`window_id`, `pid`, `app_id`, `wm_class`, `title`); `window_id` is the numeric window id from
`list_apps`, so no separate `linux-window:<id>` string form is needed.

## Environment notes

- **Wayland:** screenshot and input go through `xdg-desktop-portal`. The portal must have a
  backend matching the session (for example `xdg-desktop-portal-kde` on Plasma); the first
  screenshot may raise a system permission dialog the user has to accept. When the portal is
  missing or unauthorised, `health.degraded` and the tool result say so — the helper never
  reports a capture that did not happen.
- **AT-SPI:** element-targeted actions need accessibility enabled in the session. If it is off,
  `get_app_state` returns `accessibility_error` and an empty tree rather than a partial one
  presented as complete.
- **Window control** is per compositor; `health.windowing.backends` reports which backends
  answered here. The shipped `gnome-shell-extension/` is only used on GNOME.
