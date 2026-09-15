
---

## 附录 I — 第 9 轮（解锁后）：P7 实机验收首批结果

> 用户解锁桌面后执行。桌面锁屏阻塞解除，验收正式开始。
> `cargo test --release` **82 passed / 0 failed**；Python `pytest` **195 passed / 0 failed**。

### I.1 已验证通过（真实窗口、真实输入）

被测窗口：`ParityTarget.exe`（本轮新建的独立 WinForms 程序，含一个 TextBox + 一个 Button，
并把每次 TextChanged / Click 追加写入 `target-events.log`）。

| 验收项 | 结果 | 证据 |
|---|---|---|
| **两段式循环（无障碍路径）** | ✅ | 观察 → `click({element_index: 3})` → 刷新，全部 `ok` |
| **真实输入到达应用** | ✅ | App 侧日志 `button-clicked`，且按钮回调把文本框改成 `clicked-by-dsh` |
| **`set_value`** | ✅ | `set_value({element_index: 2, value: "parity-written-by-dsh"})` → `ok`；App 日志 `text=parity-written-by-dsh`；刷新后树里可见 `Value: parity-written-by-dsh` |
| **坐标路径** | ✅ | `click({window, screenshotId, x, y})` → `ok` |
| **坐标越界拒绝（官方文案）** | ✅ | `point (99999.0, 150.0) is outside viewport { originX: 360, originY: 270, width: 960, height: 630 }` |
| **坐标门禁（命中非目标窗口）** | ✅ | `point (1302, 692) is over Parity Target (ParityTarget.exe), not target window … (msedge.exe); activate the target or take a fresh screenshot before retrying` |
| **终端程序策略** | ✅ | 目标窗口宿主为 `pwsh.exe` 时，`click`/`set_value` 报 `Do not automate terminal applications.` |
| **AX diff 顺序** | ✅ | 观察 → 观察（无变化）→ **逐字** `no accessibility-tree change` → `disableDiffing` 全量 → **仅截图**（`accessibility=null, shots=1`）→ 观察 → **全量树**（官方规则：截图观察后必须全量） |
| **AX 树行格式** | ✅ | `[9] 编辑 "Parity probe label" {x: 48, y: 137, width: 540, height: 35} (settable, string) Value: parity-initial ID: ParityBox` —— 序号、角色、名称、包围盒、圆括号状态、Value/ID 全部符合官方模板 |
| **多窗口截图空间** | ✅ | `get_window_state` 返回 `screenshot-N` + origin/size，截图能定位到窗口 |

**结论：模型与真实桌面之间的核心闭环（看 → 点 → 再看 → 文本写入）在实机上成立。**

### I.2 本轮修掉的第二个真实缺陷（FIX-1 的残留）

FIX-1（第 1 轮）删除了光标窗口的显式捕获排除，但**光标仍然不出现在截图里**。本轮用三层证据定位到真正原因：

1. **窗口状态探测**：光标窗口 `DshComputerUseCursorOverlayPointer` 可见、126×126、位置正确，
   但 `GetWindowDisplayAffinity` = **`0x00000011`（WDA_EXCLUDEFROMCAPTURE）**。
2. **原子验证**（单 helper，按 PID 过滤）：点击后、任何 observe 之前 affinity = `0x00000000`；
   **一次 observe 之后又变回 `0x00000011`**。
3. **根因**：`capture.rs` 里有一条兜底扫描 `exclude_overlays()` → `OVERLAY_CLASSES`，
   它同时包含显示层与**光标**两个窗口类；而 `main.rs` 的 `get_window_state` 每次都调用
   `overlay::exclude_overlay_from_capture()`，后者遍历 `overlay::hwnds()`（含光标窗口）并逐个排除。
   我第 1 轮只删了显式调用，**被这条全覆盖**。

**修复**：

- `capture.rs::OVERLAY_CLASSES` 只保留显示层两个类，移除两个光标类（并写明为什么不能加回来）
- `overlay::exclude_overlay_from_capture()` 改为**只排除非光标窗口**，新增 `is_cursor_overlay()`（按窗口类判定）
- 运行时诊断确认：`id=… is_cursor=true` 被跳过，只有显示层被排除

**修复后**：同一 before/after 对比从 **0 个差异像素** 变为 **40 个差异像素**（出现变化）。

### I.3 未定论：光标是否真的出现在模型读到的截图里

诚实记录：修复后差异像素从 0 涨到 40，但**我未能确证那 40 个像素就是光标**。

- 差异区域 bbox 为 `949,95 .. 959,108`（画面右上角），落在窗口标题栏按钮附近，也可能是 hover 高亮
- 全图按光标特征色（`#080808` 填充、白色描边、强调色光晕的低透明度混合值）搜索：
  BEFORE=2096、AFTER=2105，**只多 9 个像素**，不足以构成一个光标字形
- 因此**光标到底有没有被捕获，尚无定论**；需要一次干净的对照实验（例如把光标定位到画面中央后立刻同批截图，并排除标题栏 hover 干扰）

**这是一个明确的待办，不是已完成项。**

### I.4 仍未验证的 P7 项

- 光标运动观感（46° 双段外凸、弹簧手感、按压态）—— 需录屏
- Esc 中断（物理按键 → 官方中断文案 + 后续调用被拒）—— 需人工按键
- 人机输入失效（手动点目标窗口后下一次输入应被拒）—— 需人工操作
- `launch_app` 审批两条路径（批准 / 拒绝）—— 需 harness 审批 UI 交互

### I.5 新发现的次要不一致

截图 data URL 的 MIME 声明为 `image/png`，但字节实际是 **JPEG**（`FF D8 FF E0 … JFIF`）。
模型侧按声明类型解码，视觉上不影响；但若要严格对齐，应改成 `image/jpeg`。已记入手册待办。

### I.6 本轮新增工具

| 文件 | 用途 |
|---|---|
| `parity/ParityTarget.exe`（源码 `ParityTarget.cs.txt` + `build-target.ps1`） | 独立 WinForms 被测窗口，记录 TextChanged/Click 到 `target-events.log` |
| `parity/smoke-twocell.mjs` | 单进程持久会话的两段式循环测试（观察→动作→刷新→校验） |
| `parity/smoke-diff-seq.mjs` | AX diff 与「仅截图观察」的顺序验证 |
| `parity/atomic-cursor-check.mjs` + `probe-cursor-z.ps1` | 按 PID 原子的光标窗口亲和性验证 |
| `parity/check-fix1.mjs` + `diff-shots.ps1` + `find-cursor.ps1` | 光标可见性的像素级对照 |
| `parity/integrity-check.ps1` | 交付完整性核验 |
