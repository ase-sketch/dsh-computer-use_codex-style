
---

## 附录 A — 实施进度（本轮已完成）

> 本轮把 P0 / P5.0 / P1 / P2 / P5(sidecar 侧) / P3(颜色 + 光标运动学) 落到代码。
> `cargo test --release` **69 passed / 0 failed**（原基线 54 passed / 1 failed）。

### A.1 已完成

| 计划项 | 落地 | 验证 |
|---|---|---|
| **FIX-1 光标不再被排除出截图** | `overlay/mod.rs` 删除 3 处对 cursor 窗口的 `SetWindowDisplayAffinity` | `WDA_EXCLUDEFROMCAPTURE` 现在只出现在 banner 路径 |
| **FIX-2 Esc 吞掉 + exit(130) + marker** | `interrupt::mark_interrupted()` 写 `<DSH_HOME>/cache/computer-use/interrupts/<session>/<turn>` + `eprintln!` + `process::exit(130)`；`keyboard_proc` 不再落回 `CallNextHookEx` | 编译 + 分支检查 |
| **FIX-3 一个 helper 服务多 turn** | `interrupt::request_restart()/take_restart()` + `state::reset_turn_state()` + serve 循环 drain；`end_turn` 不再永久置位 `ENDED` | 新增单测 |
| **FIX-4 CLI 对齐官方** | `main.rs` 只剩 `--parent-pid` / `--system-cursor-manager` / `--previous-notify`；未知 flag `exit(2)`；allowlist 走 `DSH_COMPUTER_USE_ALLOWED_APPS` | 实机 `--ttl-ms` → `exit=2 unknown argument: --ttl-ms`；`--parent-pid=123` 也被拒 |
| **FIX-5 批准文案 + riskLevel** | 拒绝文案改官方 `Computer Use was not approved to use <name>`；新增 `APPROVAL_REQUIRED_PREFIX`；`policy.rs` 加入官方 ~110 杀软 + ~20 密码管理器 + 16 shell 窗口清单与 `risk_level()` | 实机 `get_window` → `Computer Use requires approval to use explorer.exe` |
| **P1 官方 13 方法** | `WINDOW2_CORE` 收敛为官方 13；`click_element`/`scroll_element` 不再暴露为工具 | 实机 `tools?surface=computer` → `count=13` 且名单一致 |
| **P1 描述逐字（8 处）** | `window(purpose)` 参数化；`launch_app.app` 补 `.exe` 分句；`press_key.key` 补别名段；去掉塞进 schema 的 guidance 句；补 `Scroll Left/Right` | `computer_is_exactly_the_official_thirteen` |
| **P1/P2 disableDiffing** | 接受 `disableDiffing` / `disable_diffing` / `disableDiff` | 测试 + schema |
| **P2 AX diff** | `uia::tree_diff()`：无变化输出逐字 `no accessibility-tree change`，否则 `removed:` / `added/changed:`；screenshot-only 后强制全量树 | 3 个 diff 单测 |
| **P2 AX 行语法** | 主状态列表改官方圆括号；`truncated_label` 对齐 `(truncated: {role} "{name}", omitted {n} children)` | 单测 |
| **P3 颜色** | `ACCENT_HEX = "#339cff"`（官方），`ACCENT_FALLBACK = rgb(1,105,204)`；`pick_ink_color` 4.5/4.8 + 20 次二分压暗；新增 `shadow_color()`（0.644 / 0.51） | 4 个单测 |
| **P3 光标运动学** | 新模块 `overlay/motion.rs`：三档距离判据、长距离时长多项式、60Hz 弹簧积分、`Scale` 挤压 | 6 个单测 |
| **P3 光标接入** | `play_cursor` 用 `motion::plan/keyframes` 60Hz 逐帧驱动；UI 循环运动期 16ms 唤醒；新增 press/release 调度 | 编译 + 绘制路径 |
| **P5 sidecar** | `unref` + `process.once('exit', kill)`；超时默认杀进程并 reject 全部 pending；`exit 130` → 官方 `USER_INTERRUPT_MESSAGE`；`ensureTurn()` 在 turn 变化时先发 `end_turn`；超时统一 10s / 15s | 代码级 |
| **P5 配置面** | `index.js` 增 `timeoutMs`/`launchAppTimeoutMs`/`preserveHelperOnTimeout`，`ttlMs` 默认改 0；`cordis.patch.yml` 同步；只读发现（`list_windows`/`list_apps`/`get_window`）在锁屏下可用 | 实机锁屏态 `list_apps` 可用 |
| **陈旧测试修正** | `app_catalog` 那条与现行实现矛盾的用例改为 AppsFolder 计划 + 无 canonical id 用例 | 套件全绿 |

### A.2 环境阻塞（非代码缺陷）

实机验证 `get_window_state` 时桌面**无前台窗口**：helper 与独立的 pwsh 探测在同一时刻都得到 `hwnd=0 / pid=0`。
`require_unlocked()` 因此报 `foreground window did not report a process id` —— 与官方一致（锁屏/无前台时停止），
**不是回归**。P7 的实机验收（截图可见性、AX diff 端到端、光标动画观感）需在有前台窗口的交互会话里补做；
已备好 `parity/smoke-axdiff.mjs`。

### A.3 尚未开始

- **P3 剩余**：13 点光标字形 + 强调色 blur 光晕 + `dpi/96` 缩放；提示条边框脉冲 `0.5→1.0→0.76` + shimmer 扫光 + 药丸阴影
- **P4**：`guidance.md` + `harness.md` 接入 `native_prompt()`、删 TTL 段与 shell 禁令、补 16 条安全禁令
- **P6**：浏览器 75+6+13 命令表与 payload schema
- **P7**：实机验收

### A.4 与计划的偏差（已在实现中记录理由）

1. allowlist 落点：计划写“sidecar 侧过滤”，实施改为**环境变量 `DSH_COMPUTER_USE_ALLOWED_APPS`**，
   让二进制保持官方 CLI 面，同时仍由 helper 的 `policy::deny_allowed_apps` 强制（不在 JS 层，防绕过）。
2. `pick_ink_color`：Ghidra 常量表两处比较都用 `(1,1,1,1)`，字面反编译有字节序歧义。
   实施采用已文档化语义（黑 4.5 / 白 4.8 / 否则二分压暗），并在 R3 下标注待官方实机取色复核。
3. 光标运动用**Rust 逐帧采样**而非 DirectComposition 表达式动画：控制点/时长/弹簧参数与官方同源，
   但不依赖 `CreateExpressionAnimation` 在目标机的可用性。
4. `launch_app` 的 approve 兜底：`tool.js` 仍传 `app`，`launch_unapproved()` 因此把 `app` 同时当 `displayName`；
   友好名需从 `app_catalog` 解析结果回填 —— 记为 P1 尾项。
