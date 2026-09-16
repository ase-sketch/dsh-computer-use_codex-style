## Linux P2 window2 API Reference (Codex Parity Surface)

Use this as the supported Linux window2 Computer Use API surface exposed by `helper-linux` in P2.
This surface provides **13-tool Codex parity** on Linux desktop sessions, matching the Windows window2 contract defined in `references/api.md`.

```ts
import { sky } from "@oai/sky";

const apps = await sky.list_apps();
const candidate_windows = apps.flatMap((app) => app.windows);
// Select target app and window before acting.
// Each action targets a specific Window object.

interface LinuxWindow2ComputerUseClient {
  list_windows(): Promise<Array<Window>>; // Enumerate open targetable windows (EWMH on X11).
  get_window(input: GetWindowInput): Promise<Window>; // Rehydrate a known window by id.
  list_apps(): Promise<Array<ListAppsApp>>; // List installed applications and their open windows.
  launch_app(input: LaunchAppInput): Promise<void>; // Launch application by identifier or desktop entry.
  get_window_state(input: GetWindowStateInput): Promise<WindowState>; // Capture screenshot and AT-SPI accessibility tree.
  click(input: ClickInput): Promise<void>; // Click an indexed accessibility element or window coordinates.
  press_key(input: PressKeyInput): Promise<void>; // Press a key or '+'-separated chord (keysym format).
  type_text(input: TypeTextInput): Promise<void>; // Type UTF-8 text into focused element.
  scroll(input: ScrollInput): Promise<void>; // Scroll by delta from specific coordinates.
  set_value(input: SetValueInput): Promise<void>; // Replace value of an indexed editable element.
  drag(input: DragInput): Promise<void>; // Drag between window-relative coordinates.
  perform_secondary_action(input: PerformSecondaryActionInput): Promise<void>; // Invoke secondary action on indexed element.
  activate_window(input: ActivateWindowInput): Promise<void>; // Bring open window to foreground.
  target: "linux";
}

type Window = {
  app: AppIdentifier; // Desktop app identifier (e.g. "org.gnome.TextEditor", "firefox")
  id: number; // Numeric window identifier (X11 Window XID or Wayland target ID)
  title?: string; // User-visible window title
};

type GetWindowInput = {
  app?: AppIdentifier;
  id: number;
};

type ListAppsApp = {
  displayName?: string;
  id: AppIdentifier;
  isRunning?: boolean;
  lastUsedDate?: string;
  useCount?: number;
  windows: Array<Window>;
};

type LaunchAppInput = {
  app: AppIdentifier;
};

type GetWindowStateInput = {
  include_screenshot?: boolean; // Defaults to true
  include_text?: boolean; // Defaults to false; set true to request AT-SPI accessibility tree
  window: Window;
};

type WindowState = {
  accessibility: AccessibilityState | null;
  screenshots: Array<Screenshot>;
  window: Window;
};

type AccessibilityState = {
  tree?: string; // Tree representation with numbered element indexes
  focused_element?: number;
  selected_text?: string;
  selected_elements?: Array<number>;
  document_text?: string;
};

type Screenshot = {
  id: string; // Screenshot identifier cached for coordinate actions
  url?: string; // Data URL when serialized
  zIndex?: number;
  originX?: number;
  originY?: number;
  width?: number;
  height?: number;
};

type MouseButton = "left" | "right" | "middle";

type ClickInput = {
  click_count?: number;
  element_index?: number; // AT-SPI element index from latest get_window_state
  mouse_button?: MouseButton;
  screenshotId?: string;
  window: Window;
  x?: number;
  y?: number;
};

type PressKeyInput = {
  key: string; // Keysym name or chord, e.g. "Return", "Tab", "Control_L+c", "Alt_L+F4"
  window: Window;
};

type TypeTextInput = {
  text: string;
  window: Window;
};

type ScrollInput = {
  screenshotId?: string;
  scrollX: number;
  scrollY: number;
  window: Window;
  x: number;
  y: number;
};

type SetValueInput = {
  element_index: number;
  value: string;
  window: Window;
};

type DragInput = {
  from_x: number;
  from_y: number;
  screenshotId?: string;
  to_x: number;
  to_y: number;
  window: Window;
};

type PerformSecondaryActionInput = {
  action: string; // e.g. "Raise", "Scroll Up", "Scroll Down", "Expand", "Collapse"
  element_index: number;
  window: Window;
};

type ActivateWindowInput = {
  window: Window;
};

type AppIdentifier = string;
```

---

## Parity Goals (Codex Parity on Linux)

The P2 window2 surface achieves full functional parity with the Windows Codex window2 surface:
1. **Identical 13-tool surface**: Direct parity in method names, parameter structures, and response shapes.
2. **Structured Window targeting**: Passing explicit `Window { id, app, title }` rather than loose string identifiers.
3. **Element index addressing**: Rich AT-SPI accessibility tree extraction with stable 1-based element indexes (`element_index`), enabling direct clicking, value replacement (`set_value`), and secondary action invocation.
4. **Visual overlay pill**: High-visibility status pill displayed during automation to notify human operators of active robot actions.
5. **Synthetic cursor**: Cursor movement visualization without stealing or corrupting host hardware cursor state.
6. **Freshness lease**: Tracking observation staleness and invalidating action caches on unexpected desktop state changes.
7. **Physical Escape interrupt**: Global Esc key grab halting automation immediately and cleaning up resources.

---

## Display Server Tiered Architecture

Linux desktop environments vary between X11 and Wayland. `helper-linux` uses a tiered capability architecture:

### 1. X11 Full Mode (Complete Parity)
- **Engine**: Built with `x11rb` (pure Rust X11 protocol implementation), eliminating external C library dependencies (no `libxcb-dev` needed).
- **Window Enumeration**: EWMH (`_NET_CLIENT_LIST`, `_NET_WM_NAME`, `_NET_WM_PID`) provides stable window IDs and process correlation.
- **Occluded Capture**: MIT-SHM (`XShmGetImage`) captures target windows even when partially obscured.
- **Input Injection**: XTest protocol extension reliably injects pointer and keyboard events.
- **Overlay & Cursor**: Override-redirect windows host the status pill; XFixes extension handles cursor rendering.
- **Interrupts**: Passive keygrab on `Escape` captures cancellation even while background applications hold focus.

### 2. Wayland Degraded Mode (Graceful Fallback)
- **Engine**: Bridges through XDG Desktop Portal (`org.freedesktop.portal.ScreenCast` and `RemoteDesktop`) alongside AT-SPI.
- **Capture Boundaries**: Wayland compositors prohibit direct out-of-process window frame capture. Screenshots capture desktop streams via Portal, mapping window bounding boxes where available.
- **Overlay & Grab Boundaries**: Wayland protocols strictly forbid arbitrary screen overlay pills and global keygrabs. The helper disables the overlay pill gracefully and relies on harness-level signal cancellation rather than global key intercepts.
- **Health Reporting**: `computer_use_health` transparently reports current display server mode (`x11` vs `wayland`) and degraded capability flags.

---

## Name Collisions Between the Two Surfaces

Five method names exist on **both** Linux surfaces and mean different things:
`list_apps`, `click`, `press_key`, `type_text`, `scroll`.

* On the window2 surface each acts on an explicit `Window { id, app, title }`, plus
  `element_index` where an accessibility element is addressed; `scroll` takes
  `x`/`y`/`scrollX`/`scrollY`.
* On the P1 `sky.window` surface they take the crate's own shape (an `app` string,
  absolute `x`/`y`, a P1 `direction`/`pages` scroll), which is what a P1 host sends.

Because a name alone cannot say which handler to use, a window2 turn tags the `call`
request with `surface` (a plain request parameter, not a new protocol method):

```jsonc
// window2 turn: reaches the native X11 window2 handler
{"id":1,"method":"call","params":{"name":"click","surface":"computer",
  "arguments":{"window":{"id":2097164,"app":"XTerm"},"element_index":3}}}

// P1 turn: no surface tag, keeps the sky.window handler and parameter shape
{"id":2,"method":"call","params":{"name":"click",
  "arguments":{"app":"linux-window:101","x":250,"y":350}}}
```

The eight window2-only methods (`list_windows`, `get_window`, `launch_app`,
`get_window_state`, `set_value`, `drag`, `perform_secondary_action`, `activate_window`)
have no P1 handler and always reach the window2 dispatcher, tagged or not.
An untagged `call` is therefore bit-for-bit the P1 behaviour it always was: an existing
P1 caller needs no change.

---

## Element Index Scoping and Stability

1. **Observation-bound Lifetime**:
   Element indexes (`element_index`) returned in `accessibility.tree` are valid **only** for the exact observation that produced them.
2. **Invalidation on Mutation**:
   Any action that modifies application state (typing text, clicking buttons, scrolling views) or any external window event immediately invalidates existing element indexes.
3. **The Two-Cell Loop**:
   Always follow the canonical two-cell loop when using element indexing:
   - **Observe**: Call `get_window_state({ window, include_text: true })` to read visible controls and fresh element indexes.
   - **Act**: Perform exactly one indexed action (e.g. `click({ window, element_index: 4 })` or `set_value({ window, element_index: 4, value: "text" })`).
   - **Refresh**: Call `get_window_state` again before taking the next action.
