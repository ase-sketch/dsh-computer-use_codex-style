# helper-linux Architecture and Integration Guide

`helper-linux` is the native Linux desktop automation daemon for DeepSeek Harness (`dsh-computer-use`). It bridges the DSH agent environment with Linux desktop display servers and accessibility layers.

## 1. Architectural Position

- **Upstream & Origin**: Forked from the MIT-licensed `ilysenko/codex-desktop-linux` (`computer-use-linux` crate).
- **Process Model**: Runs as a separate helper child process spawned by the plugin runtime.
- **Communication Protocol**: Communicates via standard **stdio JSONL** (line-delimited JSON messages).
  - Request: `{"id": 1, "method": "list_apps", "params": {}}`
  - Response: `{"id": 1, "ok": true, "result": [...]}` or `{"id": 1, "ok": false, "error": "..."}`

## 2. Building helper-linux

The crate source resides at the repository top level under `helper-linux/`.

```bash
# Build release binary (recommended)
cargo build -p helper-linux --release

# Or build debug binary during development
cargo build -p helper-linux
```

### Binary Artifact Paths

Build outputs are placed in:
- `helper-linux/target/release/dsh-computer-use`
- `helper-linux/target/debug/dsh-computer-use`

The plugin's `src/paths.js` discovers candidates in priority order:
1. Environment variable: `DSH_COMPUTER_USE_HELPER` (if set)
2. Local build outputs (`helper-linux/target/release/dsh-computer-use`, `target/debug/...`)
3. Shipped platform binaries (`helper-rs/bin/linux-<arch>/dsh-computer-use`)
4. Working directory fallback (`./dsh-computer-use`)

*(Exact binary search order and fallback candidates are governed by `src/paths.js`.)*

## 3. Tool Surface (P1 sky.window)

In P1, `helper-linux` exposes the 7 **sky.window** tools:

| Tool | Purpose | Primary Parameters |
|---|---|---|
| `list_apps` | Enumerate launchable apps and targetable windows | `{}` |
| `get_app_state` | Capture screenshot and AT-SPI accessibility tree | `{ app, disableDiff? }` |
| `screenshot` | Standalone window/app screenshot capture | `{ app }` |
| `click` | Click at window-relative coordinates | `{ app, x, y, click_count?, mouse_button? }` |
| `scroll` | Scroll at coordinates or within app viewport | `{ app, direction, pages?, x?, y? }` |
| `press_key` | Send key or chord (keysym format) | `{ app, key }` |
| `type_text` | Inject UTF-8 text into focused element | `{ app, text }` |

### Targeting Semantics
Targeting uses string identifiers (`app` parameter):
- Application identifier or name (e.g. `"gedit"`, `"firefox"`)
- Window-specific identifier formatted as `"linux-window:<id>"` (e.g. `"linux-window:12345"`)

## 4. Session & System Requirements

1. **Wayland & X11**:
   - On Wayland, capture and remote input use **XDG Desktop Portal** (`org.freedesktop.portal.ScreenCast` and `org.freedesktop.portal.RemoteDesktop`).
   - On X11, native X11 extensions / XTest are utilized.
2. **First-run Portal Authorization**:
   - Under Wayland, the first screenshot or input call triggers an interactive desktop authorization popup asking the user to confirm screen sharing and remote desktop access.
   - If the user dismisses or denies the prompt, the helper returns an authorization error.
3. **AT-SPI Accessibility**:
   - `get_app_state` retrieves accessibility information via AT-SPI2 D-Bus.
   - Ensure AT-SPI is enabled in your desktop environment (e.g. `gsettings set org.gnome.desktop.interface toolkit-accessibility true`).

## 5. Capability Boundaries & Graceful Degradation

- **P1 vs. P2 Window2**:
  - P1 focuses on the core 7-tool sky.window surface.
  - Windows window2 features—such as element index addressing (`element_index`), `drag`, direct `set_value`, visual overlay banner with physical Escape cancel, and UIA snapshot caching—are deferred to subsequent iterations (P2).
- **Accessibility Fallback**:
  - When AT-SPI is unavailable or disabled, `get_app_state` returns `text: ""` or omits `text`, while still returning valid screenshots. Agents can seamlessly fall back to visual inspection and coordinate-based clicking.
- **Permission Rejection**:
  - If Portal permissions are withheld, the helper fails fast with an explicit permission rejection message rather than hanging silently.
