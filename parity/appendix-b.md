
---

## 附录 B — 第 2 轮进度（P3 收尾 / P4 完成 / P6 主体）

> 本轮结束时：`cargo test --release` **76 passed / 0 failed**；Python 套件 **179 passed / 2 failed**（两条均为与本轮改动无关的历史断言，见 B.3）。

### B.1 P3 覆盖层（继续完成）

| 项 | 落地 | 证据 |
|---|---|---|
| **官方 13 点光标字形** | `overlay/mod.rs`：`CURSOR_GLYPH_POINTS`（26 floats 原样录入）替换原 7 点多边形；填充改 `#080808`、描边改白色 `2*s` | 单测 `glyph_has_the_official_point_count_and_unit_span` |
| **强调色 blur 光晕** | GDI 回退用 3 层同心强调色圆环近似（blur 在 GDI 不可用），中心与半径按官方 `(a-3s, a-2s)` / `28*s` | 代码 + 单测 |
| **DPI 缩放** | `cursor_metrics(dpi)` = `(round(dpi*1.3125), round(dpi/96*58.5))`；窗口尺寸按 sprite、位置按 hotspot（`origin = target - hotspot`） | 单测 `cursor_metrics_match_the_official_formulas`（96→126/59，192→252/117，<96 夹到 96） |
| **按压态真的会渲染** | 新增 `PRESS_ACTIVE` + `cursor_press_until` 调度；`draw_cursor_gdi(hdc, pressed)` 不再写死 `false`；`paint_cursor` 读取按压标志 | 单测 `pressed_sprite_is_smaller_than_idle` |
| **边框脉冲官方关键帧** | `pulse_opacity` 改为 `0.0→1.0, 0.5→1.0, 1.0→0.76` + `Forever`；新增常量 `BORDER_PULSE_LOW=0.76` / `BORDER_THICKNESS_FACTOR=16` / `BORDER_INNER_FACTOR=0.88`；`start_edge_breath` 的端值改用这些常量 | 单测 `border_pulse_matches_the_official_constants` |
| **边缘渐变改用官方强调色** | `linear_edge_brush` 从硬编码金色改为 `accent_color()` 派生（0.82 → 0 透明） | 代码 |

**仍未做**：shimmer 扫光（需要 mask + `Vector2(StartX + TravelX * shimmer.Progress, 0.0)` 表达式动画），药丸 drop shadow 的分离视觉层。已记入待办。

### B.2 P4 提示词接线（完成）

**根本性修正**：官方三份文档现在**原样嵌入 helper**，Rust 与 JS 读同一份文件，不可能再漂移。

```
helper-rs/assets/prompts/
  dsh-header.md        (8.5 KB) DSH 段：工具约定 + 官方 Safety/Recovery/Interrupted
  guidance.md         (13.9 KB) 与官方逐字节相同（已 Get-FileHash 验证）
  api.md               (8.0 KB) 同上
  confirmations.md     (4.6 KB) 同上
```

- `prompt.rs`：`DSH_HEADER` / `GUIDANCE` / `API` / `CONFIRMATIONS` 全部 `include_str!` 自 `assets/prompts/`；
  `native_prompt()` = header + api + confirmations + guidance。
- `dsh-plugin/src/prompt.js`：不再硬编码文本，改为运行时读取同一组文件并组合；
  资产缺失时降级到极简 fallback 并打日志。`tool.js` 的 systemPrompt section 改用 `text: () => computerUsePrompt()` 延迟求值。
- `skills/computer-use/SKILL.md` 按官方结构重写（Initialize → Act and refresh → Reading screenshots →
  Guidelines → Reading the accessibility tree → Approvals → Browser → Never），已同步到用户预设目录。

**实测到达模型的文本量**：

| 通道 | 之前 | 现在 |
|---|---|---|
| helper `prompt` RPC | 15,145 字符（缺 guidance） | **35,084 字符**（含 guidance + 16 条 Safety 禁令 + Recovery + Interrupted） |
| DSH plugin system prompt | ~2,000 字符（`prompt.js` 硬编码） | **35,079 字符**（同一份资产） |

单测钉死：包含 Safety / Recovery / Interrupted / 三份官方文档；**不含** `observation expired`、`default 15s`、
`Stale/TTL`、`Do not run pwsh, OCR, PrintWindow`（自造规则已清除）。

### B.3 P6 浏览器（主体完成）

**新增 `computer_use/browser_schemas.py`（82 条官方命令的真实 payload schema）**，并在 `browser_official.py` 中接线。

| 修复 | 之前 | 现在 |
|---|---|---|
| 命令数 | 57 | **76**（补入 `navigate_tab_url`、`tabs_content`、`tab_content_export*`、`tab_clipboard_*`、`tab_cdp_call/events`、`tab_page_assets_list`、`tab_bot_detection_report`、`webmcp_*`、`list_browsers`/`get_browser*`/`get_documentation` 等） |
| `navigate_tab_url`（官方 `Tab.goto`） | **完全缺失** | 已存在 + 完整 schema |
| 每个 alias 只有必填 `tab_id` | 全部不可用 | 高流量命令有真实 schema（见下） |

实测（`parity/check_browser.py`）：
```
create_tab props: ['session_name','tab_id','url','visible']          required: 无（url 可选）
tab_ax_action required: ['tab_id','action']                         (action 是判别联合对象)
tab_ax_get_state props: ['content','disable_diffing','tab_id']       (content 三值枚举)
mark_tab status enum: ['handoff','deliverable']                      (不再是塌缩的单义词)
playwright_locator_click required: ['tab_id','selector']             (外加 button/force/timeout_ms)
browser_setup required: ['environment']                              (+ undocumentedApiMembers/excludedDocumentation)
```

另修：`rpc.dsh_tool_list()` 现在同时接受 OpenAI `{type,function}` 信封与扁平 MCP 形状 —— 这原本是
**浏览器工具在 DSH 侧完全注册不上**的根因（`tool.js` 按 `spec.name` 过滤，而浏览器条目没有顶层 `name`）。

### B.4 本轮遗留（下一轮）

1. **P3 剩余**：shimmer 扫光、药丸 drop shadow 分层
2. **P7 实机验收**：仍受环境限制 —— 桌面无前台窗口（helper 与 pwsh 探测同时刻均 `hwnd=0/pid=0`），
   `require_unlocked()` 按官方行为拒绝 `get_window_state`。解锁后跑 `parity/smoke-axdiff.mjs`。
3. **两条 Python 历史断言**（与本轮改动无关，未改动）：
   - `test_helper_protocol.py::test_parse_tree_and_locate_helper`：断言 `locate_helper()` 必须是
     `codex-computer-use.exe` 或 None，但本机现在存在 `dsh-computer-use.exe`（DSH 自有 helper，优先级更高）。
   - `test_extension_policy.py::..._audio`：断言 `start_audio_recording` 在 `ToolExecutor` 的 `tool_names` 里，
     但该集合当前不含音频工具（`executor.py:52`）。
   两条都需要按当前设计更新断言，留待与 P6 的 Security 层一起处理。
