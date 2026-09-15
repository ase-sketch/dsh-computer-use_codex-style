
---

## 附录 C — 第 3 轮进度（P3 收尾 / P6 安全层 / 套件全绿）

> 本轮结束时：`cargo test --release` **76 passed / 0 failed**；Python `pytest` **181 passed / 0 failed**（两条历史断言已按现行设计更新）。

### C.1 P3 覆盖层（收尾）

| 项 | 落地 |
|---|---|
| **药丸 drop shadow 分层** | `attach_display` 在药丸之下插入阴影容器：用官方 `shadow_color()` 派生色、偏离 2.5 DIP、内缩 3 DIP、0.45 不透明度，视觉上是投射而非第二条药丸 |
| **shimmer 扫光** | 新增 `attach_shimmer`：`CompositionMaskBrush`（accent 0.55 为 source、三段线性渐变为 mask）+ `GeometricClip` 裁到状态文本 + `CreateVector3KeyFrameAnimation` 2.2s `Forever` 扫掠。位移语义与官方 `Vector2(StartX + TravelX * shimmer.Progress, 0.0)` 同构，但不依赖 expression animation 可用性 |

实现注记：官方用 `shimmer.Progress` 属性集驱动 mask offset；这里改成对 band visual 的 `Offset` 做关键帧，视觉等价且在 `windows 0.61.3` 上无需表达式引擎。两者都保留在常量里（`SHIMMER_OFFSET_EXPRESSION`）作为参照。

### C.2 P6 浏览器安全层

新增 `computer_use/browser_security.py`：

- **`BrowserUseSecurityError`**：与官方 `yt extends Error`（`name = "BrowserUseSecurityError"`）对齐
  - **15 个 reason** 全表 + `decision_source` + `retryable`（逐条来自官方 `Vx` 表）
  - 两条**逐字** wrapper 句：retryable（`may retry after the issue is resolved, but must not bypass browser security controls or use an indirect workaround`）与 non-retryable（`must not attempt to achieve the same outcome via workaround, indirect execution, raw CDP or browser commands, alternate browser surfaces, or policy circumvention`）
  - 未知 reason 直接 `ValueError`，防止静默降级
- **同意文案**（D2 品牌：`DeepSeek Harness`，官方为 `Codex` / `Browser use`）
  - `Allow DeepSeek Harness to access <origin>?`（`access_browser_origin`）
  - `Allow DeepSeek Harness to use your browsing history for this task?`（`sensitive_data: browsing_history`）
  - `Allow upload to <url>?` / `Allow download from <url>?`
  - `Allow DeepSeek Harness to use full CDP access on <origin>`（`riskLevel: high` + `full_cdp_access: true`）
  - `to_elicitation()` 产出官方 `codex_approval_kind: mcp_tool_call` / `connector_id: browser-use` / `persist: [session, always]` 信封
- **`approval_failure(task, reason)`**：官方 approval-mediated 句 `<name> cannot <task> because <reason phrase>.` + 8 条 reason phrase 全表
- **`policy.deny_url`** 改走安全错误分类：`javascript:`/`vbscript:`/`ms-appx:` → `navigation_url_policy_blocked`（不可重试）；锁屏 → `browser_navigation_blocked`（不可重试）

实测（`parity/check_security.py`）：15 reason、7 条 retryable、5 条同意文案、两条 wrapper、approval 句、未知 reason 拒绝，全部符合预期。

### C.3 历史断言更新（两条，均按现行设计）

1. `tests/test_helper_protocol.py`：`locate_helper()` 现在断言目标是 `dsh-computer-use.exe` **或** `codex-computer-use.exe`，并在命中 DSH helper 时额外断言它来自 `helper-rs`（DSH 自有 helper 优先级更高，这是 D5 的既有决策）。
2. `tests/test_extension_policy.py`：音频断言改为**断言门禁**——`start_audio_recording` 在 `tool_names` 内时跑完整录音周期，否则断言未注册（`KeyError`）。音频工具是门控能力，不是恒存在。

### C.4 交付物清单（<workspace>\）

| 文件 | 内容 |
|---|---|
| `README-先看这个.md` | 执行摘要：结论、5 条最高优先级缺陷、三大发现、阶段表、风险 |
| `DSH-ComputerUse-官方对齐实施计划.md` | 完整计划 + 附录 A/B/C（约 105 KB） |
| `CHECKLIST.md` | **验收清单**：每条带可复现命令；已勾选 40+ 项；P7 实机项列出解锁后的执行序列 |
| `research/analysis/01〜04-*.md` | 四份深度逆向报告（约 320 KB，三级证据） |
| `research/analysis/official-strings-full.tsv` | 官方 exe 完整字符串表（19,762 条） |

### C.5 唯一剩余阻塞

**P7 实机验收**：桌面仍无前台窗口（本轮再次确认：helper 与独立 pwsh 探测同一时刻都是 `hwnd=0 / pid=0`，`fgProc=Idle session=0`，`LogonUI` 未运行）。
`require_unlocked()` 因此返回官方文案 `foreground window did not report a process id`。
这是官方行为（锁屏时停止并请用户解锁），不是回归，也无法在代码层绕过 —— 绕过就等于放弃官方的一致性保证。

解锁后按 `CHECKLIST.md` 第 7 节执行即可；`parity/smoke-axdiff.mjs` 与 `parity/probe-fg.ps1` 已就绪。
