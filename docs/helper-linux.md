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

## 6. P2 Progress: window2 Full Surface (X11 Parity)

P2 expands `helper-linux` from the 7-tool sky.window subset to the **13-tool Codex window2 full surface**, matching Windows window2 parity.

### Key Capabilities in P2
1. **13-Tool Surface**: Support for `list_windows`, `get_window`, `list_apps`, `launch_app`, `get_window_state`, `click`, `press_key`, `type_text`, `scroll`, `set_value`, `drag`, `perform_secondary_action`, `activate_window`.
2. **Pure-Rust x11rb Architecture**: Implemented over pure-Rust `x11rb-protocol` extensions (XTest, XShm, XFixes, XInput2) without requiring external C libraries (`libxcb-dev`).
3. **Structured Window Targeting**: Fully targets `Window { id, app, title }` instances with EWMH-backed enumeration and rehydration.
4. **Element Indexing via AT-SPI**: Structured accessibility trees with 1-based element indices (`element_index`), supporting direct indexed clicking, `set_value`, and secondary actions.
5. **Experience & Safety Layer** (one layer per X session, armed by observation on **both**
   surfaces — the P1 sky.window tools and the window2 ones):
   - Status overlay pill via override-redirect window.
   - Synthetic cursor tracking with hardware pointer suppression via XFixes.
   - Freshness lease enforcement via XInput2 raw event tracking.
   - Global physical `Escape` key intercept via X11 keygrab, degrading to XInput2 raw-key
     detection with an honest `health.experience.degraded` note when the compositor already
     owns the bare Escape combination (BadAccess).
   - `health.experience` separates availability (`available`) from activation (`armed`), so an
     idle layer is never reported as if a turn were running.
6. **Tiered Display Server Architecture**:
   - **X11 Full Mode**: Complete 13-tool parity, occluded window capture via MIT-SHM, overlay pill, synthetic cursor, and keygrab interrupt.
   - **Wayland Degraded Mode**: Fallback to Portal-backed capture and input injection; overlay and global keygrabs degrade gracefully with clear status reporting in `computer_use_health`.

