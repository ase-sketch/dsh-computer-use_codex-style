
### D.5 本轮额外落地（不依赖桌面解锁的对齐项）

**launch_app 批准提示显示友好名**（原为裸 app id）

- `app_catalog::LaunchTargetInfo::display_name()`：优先 PE `ProductName` → `OriginalFilename` → 文件叶名 → 请求串；
  空白元数据被忽略，不会产出空提示
- `protocol::Error::launch_unapproved(app, display_name)`：approvalRequest.displayName 现在带用户可见名；
  app 字段仍是稳定标识（供 `x-oai-cua-approved-app` 回传与记忆匹配）
- `main.rs` 的 `launch_app` 分支传入 `info.display_name()`
- 新增 5 个单测：displayName 正确性、空白回退、风险等级（1Password → high / notepad → low）、
  四级回退链、以及真读 notepad.exe PE 版本信息

**效果**：批准 UI 从 `Allow DeepSeek Harness to use notepad.exe?` 变为 `Allow DeepSeek Harness to use Notepad?`
（官方同构：`Allow Codex to use <displayName>?`）。

> 注：本次实机 `launch_app` 仍被锁屏门禁拦下（`launch_app` 不在 `skip_lock_check` 里，与官方一致），
> 因此 displayName 的验证走单测 + 真实 PE 版本信息读取，而非端到端调用。

### D.6 本轮套件状态（最终）

- `cargo test --release` → **81 passed / 0 failed**
- Python `pytest` → **181 passed / 0 failed**
- helper `health` → `ttlMs: 0`（正常）

### D.7 P7 状态判定

| 项 | 状态 |
|---|---|
| P0 基线 / P5.0 五项缺陷 / P1 工具契约 / P2 观察语义 / P5 生命周期 | 完成，含实机验证 |
| P3 覆盖层视觉 | 代码完成 + 单测覆盖；观感验收需解锁 |
| P4 提示词接线 | 完成，字符量与内容双重验证 |
| P6 浏览器 | 命令表 + schema + 安全层完成；其余 8 项安全检查未做 |
| **P7 实机验收** | **被锁屏阻塞**（LockApp 前台，输入桌面名 Default） |

**P7 的验证脚本已就绪，解锁后一条命令即可跑完**：

```powershell
pwsh -NoProfile -File <repo>\parity\probe-fg.ps1   # 期望 hwnd != 0
node <repo>\parity\smoke-axdiff.mjs                # AX diff 端到端 + 截图可见性
# 可选：起一个稳定的被测窗口再测 element_index 点击
pwsh -NoProfile -File <repo>\parity\ax-harness.ps1
```
