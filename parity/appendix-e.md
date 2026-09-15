
---

## 附录 E — 第 5 轮：P6 安全检查全集 + 防漂移 parity 测试

> 本轮结束时：`cargo test --release` **81 passed / 0 failed**；Python `pytest` **192 passed / 0 failed**
> （新增 11 条 parity 断言）。桌面仍锁屏（同一 `LockApp` 句柄），P7 状态不变。

### E.1 P6：官方 11 项安全检查全集

新增 `computer_use/browser_checks.py`：

- **11 个 check id + 遥测 permission name 全表**（`CHECK_PERMISSION_NAMES`）—— 与官方 `:37174-37186` 逐条对应
- **三种安全模式与两张绕过表**（官方 `:20050-20064`）：
  - `""`（默认）：`bypassed = {}`、`no-consent = {}` —— 全部检查生效
  - `disabled-for-local-testing`：绕过 10 项检查、9 项免同意
  - `gaas-browser-environment`：不绕过任何检查，4 项免同意
  模式来自 `BROWSER_USE_SECURITY_MODE`；未知模式直接 `ValueError`
- **逐字拒绝句**（`denial_text()`），11 条分支全部来自官方原文，含两个特例：
  - 非 HTTP(S) 的 raw CDP：`Raw CDP requires an HTTP(S) page. Navigate to the tab first then use the CDP capability.`
  - WebMCP 页面漂移：`… cannot use WebMCP tools because the current page changed while waiting for approval.`
- **同意文案映射**（`consent_for()`），其中两项官方用第一人称：
  - `I need your permission to download assets used by <host>`
  - `I need your permission to download an asset from <host>`
  - `check-navigation-url-policy` 与 `check-url-site-status` **永不同意、直接 fail closed**（返回 `None`）
- **`BrowserSecurityPolicy`**：把决定与「问用户」分离（问用户交给 DSH approval 服务），因此无需 harness 即可单测。
  门禁方法：`assert_origin_allowed` / `assert_url_policy` / `assert_site_status_allowed` /
  `assert_upload_allowed` / `assert_download_allowed` / `assert_full_cdp_allowed` /
  `assert_page_asset_download_allowed`（同源静默放行，跨源才要同意）。

接线：`BrowserSurface.__init__` 从 `BROWSER_USE_SECURITY_MODE` 构造策略；`tab_goto` 改为官方顺序
**URL 策略 → site-status → origin 同意**（原来只调了 `policy.deny_url`）。

实测（`parity/check_checks.py`）：11 检查、3 模式、绕过计数、7 条拒绝句、3 条同意文案、
7 个门禁在严格模式全部拒绝（reason 与 retryable 正确）、批准 origin 后放行、同源素材静默放行、
local-testing 模式正确绕过、未知模式被拒。

### E.2 防漂移 parity 测试（新增 `tests/test_parity.py`，11 条）

这些断言的数字与字符串全部来自官方产物；任何一条失败都意味着**要么改动错了，要么官方 bundle 变了、所有派生值必须重新推导**。

| 测试 | 钉死的内容 |
|---|---|
| `test_computer_surface_is_exactly_the_official_thirteen` | 通过**真实 stdio 协议**问 helper，断言工具名列表与 `Window2ComputerUseClient.d.ts` **顺序与内容完全一致** |
| `test_helper_never_advertises_internal_routes` | `click_element` / `scroll_element` 永不作为工具出现 |
| `test_official_has_no_time_based_observation_expiry` | `health.ttlMs == 0` |
| `test_unknown_cli_flag_aborts_instead_of_serving` | `--ttl-ms … serve` 必须非零退出并含 `unknown argument` |
| `test_official_documents_are_shipped_verbatim` | 三份官方文档在 `assets/prompts/` 且带 Safety / Recovery / staleness 措辞 |
| `test_official_safety_denies_are_all_present` | **9 条硬拒绝逐条在 guidance 里**（终端、Run 对话框、认证对话框、密码管理器、杀软、Windows 键、年龄验证、不可信内容…） |
| `test_window_key_deny_names_every_alias` | Windows 键禁令必须列出 `Meta/Windows/Win/Cmd/Command/Super/OS` 全部别名 |
| `test_security_taxonomy_has_the_official_fifteen_reasons` | 15 个 reason + **恰好 7 条 retryable** |
| `test_security_check_catalog_matches_the_official_permission_names` | 11 检查 + 3 个关键 permission name |
| `test_empty_security_mode_enforces_everything` | 默认模式零绕过；另两模式的绕过计数为 10 / 4 |
| `test_official_browser_commands_all_have_real_schemas` | `navigate_tab_url` 存在且 required = `[tab_id, url]`；`mark_tab` 保留双 status；`tab_ax_action` 要 `action`；**tab_id-only 命令少于总数一半** |

### E.3 套件演进

| 轮次 | Rust | Python |
|---|---|---|
| 起始 | 54 passed / 1 failed | 174 passed / 7 failed |
| 第 1 轮后 | 69 / 0 | — |
| 第 3 轮后 | 76 / 0 | 181 / 0 |
| 第 4 轮后 | 81 / 0 | 181 / 0 |
| **第 5 轮后** | **81 / 0** | **192 / 0** |

### E.4 P7 状态（不变）

桌面仍处于锁屏（`LockApp` 句柄 `7471846`，输入桌面名 `Default`）。`require_unlocked()` 按官方行为拒绝输入类调用，
并报官方文案 `Windows desktop is locked (input desktop is LockApp); unlock before using computer-use`。
解锁后执行 `CHECKLIST.md` 第 7 节即可。

### E.5 剩余（均不需要解锁即可继续，但价值低于已完成项）

- `webmcp-tool-call` 的页面漂移检测（需要真实标签页导航事件，属集成层）
- `automated-safety-precheck`（GaaS 模式专用，DSH 不部署该模式）
- 风险 R1：动画时长 tick 的录屏反推（需要人眼/录屏，解锁后一并做）
- 风险 R8：AX 树 element index 承载格式的 golden sample（需要官方 exe 实机输出）
