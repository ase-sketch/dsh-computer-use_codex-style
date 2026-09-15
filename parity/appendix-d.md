
---

## 附录 D — 第 4 轮：P7 阻塞根因定位 + 锁屏检测缺陷修复

### D.1 P7 阻塞的真正原因（本轮查明）

之前三轮只看到 `GetForegroundWindow()` 返回 `NULL`，因此一直在等「桌面有前台窗口」。本轮把探测做深，
拿到了确凿结论：

```
GetForegroundWindow() = 7471846
  进程   = LockApp   (session 1)
  标题   = Windows 默认锁屏界面
  class  = Windows.UI.Core.CoreWindow
OpenInputDesktop       = 有效
input desktop name     = Default      ← 注意：不是 Winlogon
thread desktop         = Default
visible windows        = 49 个，其中 33 个有标题
```

**结论：桌面处于锁屏状态。** `LockApp.exe` 占据前台，但**输入桌面名仍是 `Default`** —— 这就是为什么
前三轮既看到「有 49 个可见窗口、输入桌面可打开」，又看到「前台窗口为 NULL」。
锁屏会话里 `GetForegroundWindow()` 在锁屏窗口之外会瞬时返回 `NULL`。

### D.2 由此发现的真实缺陷（已修）

DSH 原来的锁屏判定只看**输入桌面名**：

```rust
fn name_is_lock_desktop(name: &str) -> bool {
    lower.contains("winlogon") || lower.contains("screensaver") || lower == "lock" || …
}
```

而现代 Windows 锁屏的输入桌面名是 `Default`，**这个判定完全看不到锁屏**。于是 `require_unlocked()`
落到下一步 `require_foreground_pid()`，报出含糊的 `foreground window did not report a process id`
—— 模型拿到这句话无从判断该做什么，而官方语义是「立即停止并请用户解锁」。

**修复**（`helper-rs/src/desktop.rs`）：

- 新增 `LOCK_APP_EXE = "lockapp.exe"` / `LOCK_APP_CLASS = "Windows.UI.Core.CoreWindow"`
- 新增 `foreground_is_lock_app(pid)`：前台进程是 `LockApp.exe` 即判为锁屏
- `require_unlocked()` 顺序改为：**输入桌面名 → `LockApp` 前台 → 解析前台进程 id**
- 新增单测 `lock_app_is_recognised_as_the_lock_screen`（钉死 `Default` 不算锁屏名、`LockApp` 的官方文案）

**实机验证（改动前后对比，同一锁屏状态、同一命令）**：

| | `get_window_state` 的错误 |
|---|---|
| 改动前 | `foreground window did not report a process id`（无法据以行动） |
| 改动后 | **`Windows desktop is locked (input desktop is LockApp); unlock before using computer-use`** |

同时 `list_windows` 在锁屏下仍可用（返回 25 个窗口）—— 这是刻意的：官方提示词要求模型「锁屏时立即停止并请用户解锁」，
而它只有能枚举窗口才说得清状况。

### D.3 为什么 P7 无法由我完成

`require_unlocked()` 拒绝一切输入类调用 —— 这是**官方行为**，不是 DSH 的偏好：

- 官方 rdata 串：`Windows desktop is locked (input desktop is <name>); unlock before using computer-use`
- 官方 guidance：「If the Windows desktop is locked, stop immediately and ask the user to unlock the desktop.
  Do not try to interact through `LockApp.exe`。」

绕过它就等于放弃本次对齐的核心目标之一。**解锁桌面是用户侧动作**，我无法代劳。

因此我把 P7 的验证脚本做成**解锁后一条命令即可跑完**：

```powershell
# 1) 确认已解锁（期望 hwnd != 0）
pwsh -NoProfile -File <repo>\parity\probe-fg.ps1
# 2) AX diff 端到端 + 截图可见性
node <repo>\parity\smoke-axdiff.mjs
```

另备 `parity/ax-harness.ps1`（一个带 TextBox/Button 的真实窗口，会自行抢前台、2 分钟后自动关闭），
可在解锁后当作稳定的被测目标，用来验证 AX 树里的 `[index] role "name" {bounds}` 行与 element_index 点击。

### D.4 本轮套件状态

- `cargo test --release` → **77 passed / 0 failed**（新增锁屏检测单测）
- Python `pytest` → 181 passed / 0 failed
