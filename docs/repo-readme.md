# computer-use

LLM-agnostic Computer Use driver reconstructed **1:1 with Codex Windows window2** (`@oai/sky` + plugin `26.903.61454`).

Official prompt files live in `computer_use/prompts/` (`SKILL.md`, `guidance.md`, `confirmations.md`, `api.md`). The published tool table is the window2 method list, not a simplified alias set.

## Official tools

`list_windows`, `get_window`, `list_apps`, `launch_app`, `get_window_state`, `click`, `press_key`, `type_text`, `scroll`, `set_value`, `drag`, `perform_secondary_action`, `activate_window`

`get_window_state({window})` defaults to screenshot + `accessibility: null`. Pass `include_text: true` for the indexed tree. Input tools return void; refresh with a second `get_window_state` (two-cell loop).

## DeepSeek Harness plugin

This repository root **is** the Cordis bundle (official layout: `package.json` + `cordis.patch.yml` + entry modules): HOST sidecar (`dsh-computer-use`) + PRESET tools (`dsh-computer-use/tool`). Codex is not required. Install with `dsh plugin --profile web add <repo>` and open a session on the user preset `computer-use`. Sidecar protocol: `python -m computer_use serve`.

> Layout note: the bundle root used to be the nested `dsh-plugin/` directory and moved to the repository root. Development reports that quote the previous paths live in the local-only `analysis/` directory, which is not published.

## CLI

```bash
python -m computer_use tools
python -m computer_use prompt
python -m computer_use call list_apps
python -m computer_use call get_window_state --args "{\"window\":{\"app\":\"notepad.exe\",\"id\":1},\"include_text\":true}"
python -m computer_use --backend live call list_apps
python -m computer_use --backend helper call list_apps
python -m computer_use --backend fake --surface desktop serve
```

`helper` / `live` (when the official exe is installed) speak `codex-computer-use.exe` JSON-lines with `CODEX_CLI_PATH`. That is the same helper Codex uses for WGC, overlay, UserAssist, and approvals.

Default backend is fake (no real pointer). `--backend live` uses the official helper when present, otherwise ctypes UIA + PrintWindow.

Surfaces (default `computer` = window2 only):

```bash
python -m computer_use --surface all tools
python -m computer_use --surface browser call tab_new --args "{\"url\":\"https://example.com/\"}"
python -m computer_use --no-steal-focus call click --args "{\"app\":\"notepad.exe\",\"element_index\":1}"
```

`--surface all` adds mac `get_app_state`/`paste`/`select_text`, browser `tab_ax_*` + `tab_dom_*`, and harness `batch_actions` / `session_note`. Tool results compact screenshots (ids only, no base64) unless `emit_image` is true.

Set `COMPUTER_USE_CDP=1` to attach Browser tools to a live Chrome/Edge DevTools WebSocket (`--remote-debugging-port`, `--remote-allow-origins=*`). Default stays the in-memory fake tab.

DOM CUA tools: `tab_dom_get_visible_dom`, `tab_dom_click` / `double_click`, `tab_dom_type`, `tab_dom_keypress`, `tab_dom_scroll`.
Playwright tools: `tab_pw_locator`, `tab_pw_get_by_role` / `text` / `label`, `tab_pw_click`, `tab_pw_fill`, `tab_pw_count`, `tab_pw_inner_text`, `tab_pw_evaluate`. Live path uses `chromium.connect_over_cdp`.

IAB: `browser_detect` / `browser_set_visible` / `tab_list` / `tab_mention_resolve`. Hidden by default; `codexSessionId` 检测条件与官方一致。
Chrome 扩展（接管登录态标签）：加载 `computer_use/chrome_extension/`，Python `ExtensionHub.start(8765)`。扩展枚举当前 profile 的 tabs，`claim` 走 `chrome.debugger.attach`。
Download 事件流：CDP `Browser/Page.setDownloadBehavior` + `downloadWillBegin`/`downloadProgress`，失败则 `credentials:include` fetch；Playwright `page.on('download')` 接到 `path/suggestedFilename/url/cancel/failure`。
helper named pipe：`COMPUTER_USE_PIPE_SPAWN=1` 时 spawn 带 `SKY_CUA_NATIVE_PIPE=1` 并发现 `\\.\pipe\*computer-use*`。
`browser_id`、locator `getByRole`→`getByText` 句柄链、`tab_dev_logs.url`、`documentation_get` 含官方插件 docs 树、named pipe `SKY_CUA_NATIVE_PIPE` 长度前缀 JSON-RPC。

## Any LLM

```python
from computer_use import (
    FakeDesktop, ComputerUse, ToolExecutor, SkyHarness,
    openai_tools, system_prompt,
)

executor = ToolExecutor(ComputerUse(FakeDesktop()))
tools = openai_tools()
prompt = system_prompt()
harness = SkyHarness(executor)
harness.initialize("notepad.exe")
harness.observe(include_screenshot=False, include_text=True)
harness.act_and_refresh("click", {"element_index": 1})
```
