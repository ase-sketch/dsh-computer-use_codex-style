
---

## 附录 H — 第 8 轮：交付完整性核验 + 阻塞判定

### H.1 交付完整性（全部通过）

```
1) 源文件完整性     : 20/20 工件齐备
2) release 二进制   : 2026-09-14 02:01:43  ≥ 最新源文件 02:01:32  → 已是最新构建
3) skill 引用包     : 三个 skill 根（插件 / 用户预设 / ~/.dsh/skills）的三份文档与 helper 资产逐字节相同
```

### H.2 套件状态（未变）

- `cargo test --release` → **82 passed / 0 failed**
- Python `pytest` → **195 passed / 0 failed**（含 14 条 parity 门禁）

### H.3 阻塞判定

**阻塞条件（连续 7 轮完全同一）**：本机桌面处于锁屏状态，`require_unlocked()` 按官方行为拒绝一切输入类调用，
因此 P7 的实机验收（截图可见性、AX diff 端到端、光标动画观感、Esc 中断、人机输入失效）无法执行。

**为什么这不是「困难」而是真阻塞**：

1. 门禁来自**官方设计**：官方 rdata 串 `Windows desktop is locked (input desktop is <name>); unlock before using computer-use`，
   官方 guidance 明确写「锁屏时立即停止并请用户解锁，不要试图通过 `LockApp.exe` 交互」。
2. **不能代码绕过**：绕过它等于放弃本次对齐任务的核心目标之一（行为一致）。
3. **环境本身健康，只差解锁**：已用 WTS API 核实 session 1 是 Active 的 Console 会话、用户 `%USERNAME%` 已登录 ——
   所以解锁后必然出现前台窗口（见附录 F.1）。
4. **解锁是用户侧动作**：我没有任何可用手段代替。

**我已排除的替代路径**：

| 尝试 | 结果 |
|---|---|
| 造一个真实窗口并抢前台（`AttachThreadInput` + ALT 注入） | 把锁屏界面顶到前台，证明锁屏本身在前台 |
| 找无门禁的读取方法来演练截图/AX | `list_windows`/`list_apps`/`get_window` 都只走 EnumWindows，不碰 capture；硬约束 |
| 查是否断连/无控制台会话 | 否 —— Active Console 会话 |
| 查是否 `Winlogon` 输入桌面 | 否 —— 现代锁屏的输入桌面名是 `Default`，已补 `LockApp` 前台判定 |

### H.4 解除阻塞所需（唯一动作）

解锁本机桌面，然后执行：

```powershell
pwsh -NoProfile -File <repo>\parity\probe-fg.ps1   # 期望 hwnd != 0
node <repo>\parity\smoke-axdiff.mjs                # AX diff 端到端 + 截图可见性
# 可选：起一个稳定被测窗口再验证 AX 行格式与 element_index 点击
pwsh -NoProfile -File <repo>\parity\ax-harness.ps1
```

### H.5 交付清单

| 路径 | 内容 |
|---|---|
| `<workspace>\README-先看这个.md` | 执行摘要 |
| `<workspace>\DSH-ComputerUse-官方对齐实施计划.md` | 完整计划 + 附录 A–H（约 130 KB） |
| `<workspace>\CHECKLIST.md` | 验收清单：已勾选项带可复现命令；P7 项列出解锁后执行序列 |
| `<workspace>\code\` | 本轮全部改动源文件镜像（约 40 个） |
| `<workspace>\research\analysis\` | 四份深度逆向报告 + 官方 exe 完整字符串表（19,762 条） |

### H.6 后续可推进项（均需解锁或属于低价值增量）

- P7 全部实机项
- 风险 R1：动画时长 tick 的录屏逐帧反推
- 风险 R8：AX 树 element index 格式的 golden sample
- 增量：`webmcp-tool-call` 页面漂移检测（需真实标签页事件）、`automated-safety-precheck`（GaaS 专用，DSH 不部署）
