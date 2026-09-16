# helper-linux 架构与集成指南

`helper-linux` 是 DeepSeek Harness 插件 `dsh-computer-use` 在 Linux 平台上的原生桌面自动化辅助进程（daemon），负责打通 DSH Agent 与 Linux 桌面显示服务及无障碍服务。

## 1. 架构定位

- **上游与来源**：Fork 自 MIT 协议开源项目 `ilysenko/codex-desktop-linux` 的 `computer-use-linux` crate。
- **进程模型**：作为独立的子进程由插件 Host / Sidecar 拉起。
- **通信协议**：采用标准 **stdio JSONL**（逐行 JSON 数据流）协议：
  - 请求：`{"id": 1, "method": "list_apps", "params": {}}`
  - 响应：`{"id": 1, "ok": true, "result": [...]}` 或 `{"id": 1, "ok": false, "error": "..."}`

## 2. 构建 helper-linux

helper-linux 源码位于仓库顶层 `helper-linux/` 目录。

```bash
# 构建 Release 版本（推荐生产使用）
cargo build -p helper-linux --release

# 或构建 Debug 版本（本地联调）
cargo build -p helper-linux
```

### 产物候选路径

构建产物默认生成在：
- `helper-linux/target/release/dsh-computer-use`
- `helper-linux/target/debug/dsh-computer-use`

插件运行时通过 `src/paths.js` 动态查找可用二进制候选：
1. 环境变量：`DSH_COMPUTER_USE_HELPER`（若配置则最高优先）
2. 本地 Cargo 构建产物（`helper-linux/target/release/dsh-computer-use` 等）
3. 预编译发布包产物（如 `helper-rs/bin/linux-<arch>/dsh-computer-use`）
4. 工作区根目录兜底（`./dsh-computer-use`）

*(具体候选路径与发现策略以 `src/paths.js` 实现为准)*

## 3. P1 工具能力面（sky.window 风格 7 工具）

P1 阶段 `helper-linux` 对外暴露 7 个核心工具：

| 工具名 | 用途 | 核心参数 |
|---|---|---|
| `list_apps` | 列出可启动应用及当前可交互的窗口 | `{}` |
| `get_app_state` | 获取指定窗口的截图与 AT-SPI 无障碍文本结构 | `{ app, disableDiff? }` |
| `screenshot` | 单独截取指定窗口/应用的屏幕画面 | `{ app }` |
| `click` | 在窗口相对坐标处执行点击 | `{ app, x, y, click_count?, mouse_button? }` |
| `scroll` | 在指定坐标或窗口视口内滚动 | `{ app, direction, pages?, x?, y? }` |
| `press_key` | 发送单个按键或组合快捷键（keysym 格式） | `{ app, key }` |
| `type_text` | 向当前获焦元素键入 UTF-8 文本 | `{ app, text }` |

### 定位语义（Targeting）
所有操作通过字符串标识符 `app` 指定目标：
- 应用名 / Desktop Entry ID（例如 `"gedit"`, `"firefox"`）
- 显式窗口标识符字符串（格式为 `"linux-window:<id>"`，例如 `"linux-window:12345"`）

## 4. 运行环境与系统权限要求

1. **Wayland 与 X11 支持**：
   - Wayland 环境下，截图与远程输入注入基于 **XDG Desktop Portal**（`org.freedesktop.portal.ScreenCast` 与 `org.freedesktop.portal.RemoteDesktop`）。
   - X11 环境下使用原生 X11 协议 / XTest 扩展。
2. **Portal 首次交互授权弹窗**：
   - 在 Wayland 桌面（如 GNOME, KDE Plasma）中，**首次调用** `screenshot` 或输入工具时，系统桌面会弹出原生授权确认框（询问是否允许屏幕共享与远程控制）。
   - 首次运行时需提示用户在图形界面中点击“允许/共享”。若用户拒绝，调用将返回权限拒绝错误。
3. **AT-SPI 无障碍服务要求**：
   - `get_app_state` 通过 AT-SPI2 D-Bus 接口提取应用控件树。
   - 需确保桌面环境开启了无障碍接口（例如 GNOME 下执行 `gsettings set org.gnome.desktop.interface toolkit-accessibility true`）。

## 5. 能力边界与降级策略

- **P1 与 P2 window2 全表面的边界**：
  - P1 专注于 7 个核心 sky.window 工具的稳定落地。
  - Windows window2 中的元素索引定位（`element_index`）、拖拽（`drag`）、直接赋值（`set_value`）、全屏遮罩/物理 Esc 拦截 overlay、Win32 HWND 句柄快照缓存等高级能力不在 P1 范围内，规划在 P2 落地。
- **无障碍服务降级**：
  - 若系统未开启 AT-SPI 或目标应用不支持无障碍协议，`get_app_state` 中的 `text` 为空，但截图依然正常生成。Agent 应平滑降级为根据视觉截图执行坐标点击。
- **Portal 权限拒绝处理**：
  - 用户拒绝 Portal 授权时，helper 快速失败并返回明晰错误信息，避免静默卡死。
