# Computer Use Parity — 验收清单

> 来源：`<repo>\analysis\dsh-computer-use-parity-plan.md`（含附录 A/B）。
> 每条都能被「一条命令 + 一次观察」证伪。`[x]` = 已用命令验证通过。

> ⚠️ **2026-09-14 第 15 轮更正（9 路深度调研后）**：本清单有 **4 条门禁被查出「测的不是那件事」**，相关结论**作废**，
> 详见 `analysis/deep-dive/10-GAP-REGISTER.md` §1 与 `_verification-log.md`：
> **V1** 官方 guidance 覆盖 92/92（haystack 里放着 needle 原文 ⇒ gap 恒为 0）；
> **V2** 常驻段 <12,000 字符门禁测的是 helper 平面，模型实际读的是 JS 平面的 36,615 字符；
> **V3** 61 条门禁全部直接驱动 helper（0 条经过 `sidecar.js`、0 条涉及 AX 树）；
> **V4** `verify-all.ps1:44` 的 `tick=20/20` 把视觉缺陷 VIS-08 固化成期望行为。
> 另：第 13 轮「光标动画时长 374–403ms 落在模型值附近」**不是对齐证据**（官方按总时长 T 归一化，我们固定 20 帧×16ms），该数字作废。

## 0. 自动化套件

- [x] **一条命令跑完实机验收**：`pwsh -File parity/verify-all.ps1` → **61/61 PASS**
      覆盖：光标落位/像素可见/无自激前台风暴 + 截图新鲜度 + 药丸两条渲染路径 + **窗口状态 5 例** +
      **插件传输层的 10 项**（Esc 中断 5 + 人机输入 2 + launch_app 审批 3）+
      **覆盖层与真实指针的 16 项生命周期门禁** + **10 项真实 Cordis 分发的插件生命周期门禁** + 2 项源码契约门禁
      覆盖：光标落位/像素可见/无自激前台风暴 + 截图新鲜度 + 药丸两条渲染路径 + **窗口状态 5 例** +
      **插件传输层的 10 项**（Esc 中断 5 + 人机输入 2 + launch_app 审批 3）+
      **覆盖层与真实指针的 16 项生命周期门禁** + 2 项插件注册面门禁
      Esc 与人机输入由**另一个进程发不带标记的注入事件**驱动 —— 修复后它与物理事件对钩子完全等价，
      而这正是远程桌面投递用户点击的方式，所以这两项从此可无人化回归
      **第 11 节（Wave 3 新增）**：官方 vs 我们 AX 富窗口 A/B（`parity/ax-rich-parity.mjs`：树体逐字节 + 尾段 + `accessibility` 键集 + `cacheDiagnostics` 键集 + 顶层键集）· ParityTarget 前台 focused 句逐字对照 · 中断标记生命周期 5 条（`parity/interrupt-marker.mjs`）
      最终实测：**83 PASS / 0 FAIL / 0 SKIP**（Wave 3 之前为 61 条；期间一度 8 条 FAIL，全部由「陈旧 Escape 标记」这一个真 bug 引起，见登记册 §12.1）
      **第 12 节（真实任务复盘后新增）**：sidecar 级「观察 → 动作」链路（`parity/sidecar-observe-act.mjs` 8 条，真实 `Sidecar` + 真实 `turnMetaFor`）——这一节是为一次真实任务失败补的：插件把 turn id 设成每次调用都变的 `callId`，于是每次调用前都发 `end_turn`、清空观察租约，所有 click/press_key 都报「没有已捕获状态」（登记册 §13）
- [x] `cargo test --release` → **196 passed / 0 failed**（另 5 条 bin 集成测试）
      `cd <repo>\helper-rs; cargo test --release`
- [x] `python -m pytest tests -q` → **290 passed / 0 failed**
      `cd <repo>; $env:PYTHONPATH='<repo>'; python -m pytest tests -q`
- [x] **防漂移 parity 测试 11 条**（`tests/test_parity.py`）：通过真实 stdio 问 helper 断言 13 方法顺序、`ttlMs=0`、未知 flag 退出、官方三文档在库、**9 条硬拒绝逐条在 prompt 里**、Windows 键 7 个别名、15 reason + 恰好 7 条 retryable、11 检查 + permission name、默认模式零绕过、浏览器命令 schema
- [x] 插件 JS 语法：`node --check` 三个文件全过；常驻段预算由诚实门禁把守 —— `node parity/claim-prompt-budget.mjs` → `alwaysOn=10371 budget=12288 official=4370 ratio=2.37 ok=true`（Wave 1 之前是 36,615）
- [x] 插件契约（`tests/contracts.test.mjs`）→ **25/25 pass**；必须从 DSH checkout 用 tsx 跑：`cd <harness>; node --import tsx/esm --test <repo>/tests/contracts.test.mjs`

## 1. 协议与 CLI（P5.0 / P1）

- [x] 未知 flag 退出且不服务：`--ttl-ms 15000 serve` → `exit=2`，`unknown argument: --ttl-ms`
- [x] `--parent-pid=123` 被拒（官方精确长度比较）→ `unknown argument: --parent-pid=123`
- [x] `--previous-notify` 缺值 → `missing value for --previous-notify`
- [x] `tools?surface=computer` → **恰好 13 个**，名单与官方 `Window2ComputerUseClient` 逐字一致
      `list_windows,get_window,list_apps,launch_app,get_window_state,click,press_key,type_text,scroll,set_value,drag,perform_secondary_action,activate_window`
- [x] `click_element` / `scroll_element` 不再作为工具暴露（dispatch 仍保留）
- [x] `health` 返回 `ttlMs: 0`（官方无时间型过期）

## 2. 观察语义（P2）

- [x] `tree_diff` 无变化 → 逐字 `no accessibility-tree change`（单测）
- [x] `tree_diff` 有变化 → `removed:` / `added/changed:` 两段（单测）
- [x] `disableDiffing` / `disable_diffing` / `disableDiff` 三种拼写都接受
- [x] `state.last_tree_text` 存**全量树**而非 diff；screenshot-only 后强制全量（单测）
- [x] AX 行语法：**主状态列表带圆括号且位于角色与名字之间**（`1 窗格 (disabled) DropShadowTop`）；截断模板 `(truncated: {limit}, omitted {n} children)`（`limit` 是**真正触发的预算**，不是角色名）
- [x] **官方 vs 我们 AX 富窗口 A/B 门禁**（`parity/ax-rich-parity.mjs`，接进 `verify-all.ps1` 第 11 节）：同一会话驱动官方 helper 与我们的 helper 对同一窗口取树，断言**树体逐字节**、尾段结构、`accessibility` 键集（含 `cacheDiagnostics` 3 键）、角色集、状态 token 计数、字段顺序、控制类型大小写、截断标记；Word 上实测 **405 行逐字节一致**（修前 60+ 行差异）。官方 helper 一律用 `%TEMP%` 一次性 `CODEX_HOME`
- [x] 已知残留（见登记册 §11.4）：`focused_element` 取值（AX-24，官方在**非前台**窗口仍能报出「最后有键盘焦点的控件」）、`document_text` 范围（AX-27，官方给全文后缀 454 字符 / 1020 UTF-8 字节，我们给全文）
- [x] **AX 树语法已用官方 helper 本体逐字校准**（`parity/golden-ax.mjs`，详见附录 L）：
      裸序号（无方括号）、**TAB 层级且根缩进 1 层**、名称不加引号且空名整段省略、**不打印包围盒**、
      `focused_element` 字段是元素行本身（无缩进无前缀）
      依据：官方原文 + 官方 `docs/api.md`「element indexes and tab hierarchy」+ 官方 `.rdata` 无元素包围盒模板
      单测 `node_line_matches_the_official_grammar` 钉死，防止再漂移
- [x] 顺带修掉转义事故：包围盒模板 `"{{{{x: …}}}}"` 在 `format!` 下还原成 `{{x: …}}`（双大括号）
- [x] `accessibility` 字段集与官方 `docs/api.md` 逐字段一致（`tree`/`focused_element`/`document_text`/`selected_elements`/`selected_text`，后三者可选）
- [x] 注解超集的原因已定位：官方 UIA CacheRequest 缺属性 —— 用官方自己的 `set_value` 复现出
      `所需属性不在 CacheRequest 中 (0x80070057)`，**它因此改不了这个 WinForms 编辑框**，而本实现可以
- [ ] 待办：窗口 `app` 标识对齐（官方 `MSEdge` / `process:<exe path>`，本实现 `msedge.exe`）
- [ ] 待办：Chromium URL 门禁（官方对浏览器窗口要求能确定 URL，否则整轮停止；P6）
- [ ] **实机**：同一窗口连续两次 `include_text` → 第二次应为 diff 或 `no accessibility-tree change`
      `node parity/smoke-axdiff.mjs`  ← **需要桌面有前台窗口**

## 3. 覆盖层视觉（P3）

- [x] 光标窗口**不再**被 `WDA_EXCLUDEFROMCAPTURE` 排除（模型能看见自己的指针）
      → 实机复核：`overlayState.windows[]` 里 `...OverlayPointer excluded=false affinity=0`；
      曾有**四处**独立机制反复把它排除（`OVERLAY_CLASSES`、`hwnds()` 注册表、`with_overlay_hidden`、
      `exclude_overlays()`），全部改为「只碰 display overlay」，并集中到 `overlay::display_hwnds()`
      `capture::is_display_overlay()` 两个谓词上，防止第五次回归
- [x] **实机：模型自己的截图里能看到假光标**（像素级验证，不是靠人眼）
      `node parity/cursor-trace.mjs` → 扫描 `lag-a.jpg`：暗像素 bbox `(97,100)-(277,593)`，
      正是点击点 (192,504) 加上字形本体；`cursor-trace.jpg` 同理落在 (768,158)
- [x] 光标字形**尖端精确落在目标点**：窗口 `origin = target - hotspot`，字形箱原点 = hotspot
      实机：目标 (1128,428) → 全屏抓图暗像素 bbox `(1128,429)-(1213,517)`，尺寸 86×89（期望 ~88×93）
      修复前：字形画在窗口左上角、光晕被二次缩放，视觉光标比真实点击点偏了整整一个 hotspot（144dpi 下 88px）
- [x] 光晕用**真 per-pixel alpha**（`UpdateLayeredWindow` + 预乘 BGRA），不再是 LWA_COLORKEY 假透明的实心暗盘
      实测光晕中心 (1136.5,438.5) vs 期望 (1137,438)；`WDA` 不受影响；`SetLayeredWindowAttributes` 失败时自动回退
- [x] 官方 13 点字形（26 floats）+ `#080808` 填充 + 白描边 `2*s` + 强调色光晕（单测：点数与单位跨度）
- [x] DPI：`cursor_metrics(96)=(126,59)`、`(192)=(252,117)`、`<96` 夹到 96（单测）
- [x] 光标按 hotspot 定位：`origin = target - round(dpi/96*58.5)`
- [x] 按压态会渲染（`PRESS_ACTIVE` + 调度释放；`pressed_sprite_is_smaller_than_idle`）
- [x] 运动学：`<0.5px` 吸附 / `≤196px` 单段 `0.24s` / `>196px` 46° 双段外凸（6 个单测）
- [x] 弹簧积分：60Hz、ζ=1.68/1.8、`|v|` eps、上限 20 帧；端点精确落位（单测）
- [x] `Scale` 挤压 `1/(1+1.5*min(|v|/3000,1))`（单测：运动中挤压、终点复位）
- [x] 强调色 `#339cff` + `rgb(1,105,204)` 回退 + 4.5/4.8 对比度 + 20 次二分压暗（4 个单测）
- [x] 阴影系数 `r'=(1-r)*0.644+r, g'=g*0.51, b'=b*0.51`（单测）
- [x] 边框脉冲官方关键帧 `1.0 → 0.76` + `Forever`（单测）
- [x] 药丸 drop shadow 分层（偏离 2.5 DIP、内缩 3 DIP、0.45 不透明度）
- [x] shimmer 扫光（mask 渐变 + 2.2s 无限偏移扫掠，官方 `Vector2(StartX + TravelX * Progress, 0.0)` 同构）
- [ ] **实机**：`SetCursorPos(target)` 先于动画启动（输入零延迟）—— 需人眼/录屏确认

## 3a. 状态药丸（实机像素验证）

> **重要更正（第一次）**：曾一度判定「DirectComposition 在本机不呈现」——那是误判。
> 真相是 `SetWindowDisplayAffinity` 只能由**拥有该窗口的进程**修改，探针从外部清除
> 亲和性会静默失败；药丸一直被正确地排除在截图之外（这是**官方设计**：药丸给人看，
> 不给模型看）。helper 自己跳过排除后才拍到药丸。
>
> **重要更正（第二次，2026-09-15 用户实机）**：上面那句「药丸给人看」在本机其实**不成立**。
> 操作者两次报告「只有假光标、屏幕上看不到药丸」，A/B 实机对照（同一 helper、同一
> DirectComposition 路径、同一位置，唯一变量是亲和性）：
>
> | 捕获排除 | 屏幕顶部正中（用户肉眼） | 截图里 |
> |---|---|---|
> | `WDA_EXCLUDEFROMCAPTURE`（旧默认） | **没有药丸** | 没有药丸 |
> | 不设亲和性 | **有药丸** | 有药丸 |
>
> 即：在部分 Windows/DWM/GPU 组合下，给 layered + DirectComposition 的药丸窗口打上
> `WDA_EXCLUDEFROMCAPTURE` 会让 DWM **连屏幕上都不再合成**它的内容；窗口状态
> （`IsWindowVisible=true`、`DwmGetWindowAttribute(DWMWA_CLOAKED)=0`、rect 正确、
> `exStyle=0x80800A8`）全部正常，所以任何只看 API 的检查都发现不了。
> 更糟的是亲和性**不可逆、且会累计**：`get_window_state` 每次都再打一遍，于是第一次
> 观察之后药丸对整个会话都不可见。
>
> 结论：默认改为**只在该次截图期间隐藏药丸**（合成器把 root opacity 归零 + `DwmFlush` +
> 丢弃截图前停放的旧帧），亲和性保留为 `overlayCaptureExclusion=wda` 可选模式。

- [x] 药丸在屏幕上真实渲染（DirectComposition 默认路径）：
      `$env:DSH_CU_OVERLAY_CAPTURABLE='1'; node parity/pill-probe.mjs` →
      药丸矩形内 5763 个强调色像素，bbox (1028,14)-(1532,62)，采样值 `51,156,255` = `#339cff`
- [x] 药丸**默认不出现在模型自己的截图里**，而屏幕上一直在：默认 `overlayCaptureExclusion=mask`
      （单次截图期间合成器隐藏 + 丢弃旧帧）；`wda` 为可选（官方亲和性，本机会连屏幕上一起消失）；
      `DSH_CU_OVERLAY_CAPTURABLE=1` 完全关闭排除，供像素诊断使用
- [x] 文案为 DSH 品牌（D2）：左 `DeepSeek Harness is using your computer`、右 `Esc to cancel`
- [x] 新版 `UpdateLayeredWindow` **回退渲染器**（`DSH_CU_ULW_OVERLAY=1` 强制启用，
      `attach_display` 失败时自动启用）：同样 5627 个强调色像素，含 1.2s `1.0 → 0.76` 边框脉冲
      （采样 55,140,211 正是 0.76 不透明度叠加桌面背景的结果）
- [x] 药丸诊断已进 `overlayState`：`displayStep` / `pillLayout` / `pillSprite` /
      `pill{builds,buildFails,pushes,pushFails,paintCalls}` / `pumpPill`

### 3a-2. 生产默认下的「既能看见、又不进截图」门禁（第 15 轮）

> `parity/pill-capture-mask.mjs`（已并入 `verify-all.ps1`）同时测两端：用 `CopyFromScreen`
> 读**操作者看到的桌面**，用 helper 自己的 `get_window_state` 读**模型会读到的帧**，
> 并以 `overlayCaptureExclusion=off` 作为对照（证明「帧里没有药丸」不是因为药丸根本没画）。

| 模式 | 屏幕（药丸隐藏时 → 显示时 → 截图之后） | 模型帧里的强调色像素 |
|---|---|---|
| `mask`（默认） | 58545 → **97735** → **95116** | 2546 → **2501**（药丸不在帧里） |
| `off`（对照） | — | 2546 → **31004**（药丸在帧里） |

- [x] 关键坑：合成器把 root opacity 归零之后，**WGC 帧池里停放的仍是遮蔽前那一帧**，
      直接取最新帧会拿到旧画面。`CaptureJob.fresh` 会先丢弃停放帧再等新帧，门禁因此才成立
- [x] 卡死保护：遮蔽由 `CaptureMask` 命令成对下达，pump 里另有 5 秒看门狗，
      `overlayState.captureMasked` / `captureMaskCount` 可诊断
- [x] 注意：本项目原有的药丸门禁都在 `DSH_CU_OVERLAY_CAPTURABLE=1` 下测量——那个变量会
      **关掉被验证的行为**（亲和性），正是它让这个缺陷躲过了所有像素门禁

## 3b. 截图新鲜度（实机发现并修复的严重回归）

> 症状：`get_window_state` 紧跟一个动作之后，返回的图**是上一个动作之前**的画面。
> 也就是模型永远看不到自己刚做的事，只能看到上一次的结果 —— 直接毁掉「动作→验证」闭环。

- [x] 定位方法：点一次 Parity Button（应用会把文本框改成 `clicked-by-dsh`），
      700ms 后截图与点击前逐像素比对 → **0 个差异像素**；再点一次后比对 → 4509 个差异像素
      （`node parity/fresh-test.mjs` + `pwsh -File parity/fresh-diff.ps1`）
- [x] 根因：`Direct3D11CaptureFramePool` 只有一个 buffer，`TryGetNextFrame` 按**最旧优先**交付；
      buffer 满时新合成帧被丢弃，于是「本次请求拿到的是上次请求那一刻的合成」
- [x] 修复：`FrameArrived` 处理器**立即取走并保存最新帧**（`FrameSlot`），buffer 永远空闲；
      池改为 2 个 buffer；`wait_frame` 返回停放的最新帧
- [x] 复测：`fresh-0 → fresh-1` = **4509 差异像素**（修复前 0），`fresh-1 → fresh-2` = 0（稳定）
- [x] 复测：同一动作后连续三次截图**字节完全相同**且都含新位置光标
      （`lag-a/b/c.jpg` 均 35138 bytes，暗像素 bbox 都延伸到 (277,593)）

## 3d. 光标运动：用测量代替录屏（风险 R1 部分收口）

> `parity/motion-curve.mjs` 用密集轮询 `overlayState` 重建真实运动曲线（helper 每帧发布
> `cursorScreenX/Y` + `motionTick`），因此**不需要录屏**即可核对官方运动契约。

| 直线距离 | 观测帧数 | 时长 | 偏离直线的最大外凸 | 外凸比 | 落点误差 |
|---|---|---|---|---|---|
| 205 px | 191 | 391 ms | 10.7 px | 5.2% | **0.0 px** |
| 402 px | 237 | 374 ms | 36.1 px | 9.0% | **0.0 px** |
| 981 px | 194 | 403 ms | 81.0 px | 8.3% | **0.0 px** |

- [x] **落点精确**：三种距离的终点误差都是 `0.0 px`（窗口 origin = target − hotspot，字形尖端即目标点）
- [x] **双段外凸存在且随距离单调增大**：205→981 px 时外凸 10.7→81.0 px，符合官方两段贝塞尔外凸模型
- [x] 时长落在模型值附近：短程 `SHORT_DURATION_S=0.24s`，长程由 `long_duration_s(...)*0.81` 给出
      （205 px 实测 391 ms ≈ 模型 0.40 s；981 px 实测 403 ms）
- [ ] **仍未做**：与官方 exe 的逐帧对比（需要 60fps 录屏或对官方 keyframe 时间戳的静态提取），
      用于确认 `MAX_KEYFRAMES=20` 截断长动画时的观感差异

## 3c. 插件传输层与输入判据（第 11 轮：4 个真实缺陷）

> 本节全部由 `parity/verify-all.ps1` 自动复现；详见计划书附录 K。

- [x] **`call` 路径曾完全不可用**：`ensureTurn` 定义在 `Sidecar` 上却调在 helper 进程对象上
      → 每个工具调用抛 `TypeError`。之前所有实机验证都走 raw stdio 脚本、绕过插件层，所以从未暴露
- [x] **turn 状态放错类**：`turnKey`/`turnMeta` 初始化在 helper 进程对象上、在 `Sidecar` 上读取
      → 读到 `undefined` → 每次首个调用多发一个 `end_turn`；中断回调也拿到 `undefined`，拒绝逻辑被架空
- [x] **`end_turn` 自锁死**：`ensureTurn` 走 `this.rawRequest`，排在「正在等它的那个调用」之后
      → 换 turn 的第一个调用永不返回。已改为直连 helper，且仅在 helper 存活时发送
- [x] turn 流转回归：同 turn 连发 ✓ / 换 turn ✓ / helper 被杀后新 turn 自动重启 ✓
- [x] **人机输入判据在远程控制下完全失效**（真缺陷）：UU 远程用注入投递鼠标事件，
      而原判据是「`injected == 0` 才算人」→ 实测 `downs=30 injected=30 generation=0`，
      **用户抢鼠标永远不会被发现**。修复：给自己注入的事件打 `dwExtraInfo = 0x4453485500000001`，
      判据改为「无标记且非 synthetic ⇒ 人」，四类来源（本地鼠标/远程真人/自家/第三方）全部归类正确
- [x] 新增诊断：`inputMonitor.{armed,installed,synthetic,mouseEvents,mouseDowns,mouseDownsInjected,keyEvents}`
- [x] **激活失败**：`AttachThreadInput` 要求调用线程有消息队列，而 RPC 线程没有 →
      用户刚与别的窗口交互过时报 `failed to activate captured window`。
      已加 `PeekMessageW(PM_NOREMOVE)` 建队列 + `SwitchToThisWindow` + ALT 轻敲三级回退

## 3e. 窗口状态边界（第 13 轮：2 个真实缺陷）

> `parity/window-states.mjs`（状态注入 `parity/window-state.ps1`），已并入 `verify-all.ps1` 的 6 项门禁。

| 状态 | `get_window_state` | 官方文案 | activate → get_window → 重试 |
|---|---|---|---|
| 正常 | ok | — | — |
| 最小化 | 拒绝 | `window is minimized; call activate_window, refresh with get_window, then retry get_window_state` | ok → ok → **ok** |
| 被隐藏 | 拒绝 | `window is not a usable app window` | ok → ok → **ok** |
| 大部分移出屏幕 | **ok** | — | — |
| 被其它窗口遮挡 | **ok** | — | — |

- [x] 后两条 ok 证明用的是**窗口捕获而非屏幕捕获**：目标在屏幕外/被盖住仍能取到画面
- [x] **缺陷 13**：`activate_window` 无法重新显示被 `SW_HIDE` 的窗口（隐藏窗口仍可被设为前台，
      于是 `SetForegroundWindow` 成功、返回 ok，调用方重试仍失败）。已加 `ShowWindow(SW_SHOW)`
- [x] **缺陷 14**：「已经是前台窗口」被当作「已经可用」而提前返回；最小化/隐藏窗口照样是前台窗口。
      条件改为 `foreground && visible && !minimized`
- [x] 测试侧：`MainWindowHandle` 在隐藏后失真 → 改 `EnumWindows`+pid；`SW_RESTORE` 不能恢复 `SW_HIDE` → 统一先 `SW_SHOW`
- [ ] 未覆盖：跨显示器（本机单屏）、cloaked UWP 窗口、动作途中窗口被移动/关闭（需确定性用例）

## 3f. 覆盖层生命周期与真实指针压制（第 14 轮：用户报告「两个鼠标」）

> 现象：一次任务跑完后桌面出现**两个鼠标**，第二个跟随真实鼠标；残留 helper 20 分钟后仍在。
> 门禁脚本 `parity/overlay-lifecycle.mjs`（16 项）+ 探针 `parity/overlay-probe.ps1` /
> `parity/cursor-suppression.ps1` / `parity/restore-cursors.ps1`，已并入 `verify-all.ps1`。

| 阶段 | 假光标 | 真实指针被压制 | 屏幕上的指针数 | manager 子进程 |
|---|---|---|---|---|
| 空闲 | 无 | — | 1 | 0 |
| 第一次 click | 有 | **是** | 1 | 1 |
| `cancel` 之后 | 无 | 否 | 1 | 0 |
| **第二次 click（修复前）** | 有 | **否** | **2** | **0** |
| **第二次 click（修复后）** | 有 | **是** | **1** | **1** |
| `end_turn` 之后 | 无 | 否 | 1 | 0 |

- [x] **缺陷 15**：`tool.js`（用户 agent preset 作用域）注册的 `ctx.on('session/event')` **永远不会触发**。
      DSH 的 session 事件按 `scopeTarget(session, scopeOf(sessionStore.ctx))` 分发，session store 在 host 根作用域（无标签），
      agent 会话也经 host 的 `runtime.ctx.sessions.prepare(...)` 创建；`@deepseek-ai/dsh-scope` 只把事件发给 equal/ancestor 作用域的监听器
      （`packages/core/session/tests/scoped.spec.ts`：a bare session … scoped listeners never hear it），preset 是**后代** ⇒ 死代码。
      修复：turn-end 释放移到 **host 平面 `index.js`**（无标签，必然收到）+ 补 `session/disposed`；`tool.js` 不再注册（注释说明原因）
- [x] **缺陷 16**：`stop_system_cursor_manager()` 把 manual-reset 的 `CursorShutdown` 事件 SetEvent 后**从不 Reset**，
      而 `windows-rs` 的 `HANDLE` 没有 `Drop`（helper 里 `CreateEventW` 的句柄一直留着）⇒ 命名对象活着且保持 signaled；
      下一次 `show()` 启动的 manager 子进程打开的是**同一个已 signaled 对象**，立刻走 shutdown 分支退出 ⇒ **压制不再发生** ⇒ 两个鼠标。
      修复：每次 spawn 前 Reset shutdown/restore；stop 时 kill 后 Reset；`blank_and_set()` 返回成功与否、只有成功才 ack；
      `show()` 用 **ack 事件**验证压制生效并重试一次；官方 `schedule system cursor re-suppression`：可见期间每 4s 重新压制（对方进程恢复光标后自愈）
- [x] 兜底（非官方契约）：可见但 120s 无任何 RPC 时自行隐藏覆盖层（`DSH_CU_OVERLAY_IDLE_HIDE_MS`）——官方 helper 是逐 turn 的短命进程，本实现跨 turn 复用，需要一个有界兜底
- [x] 可靠检测方法已标定：`SetSystemCursor` 只替换光标**内容**、句柄不变，比较 `hCursor` 与 `LoadCursor(IDC_ARROW)` **证明不了任何事**
      （已用人工 `SetSystemCursor(blank)` 标定）；可靠信号是图标的彩色位图：被置空的光标是单色的（`hbmColor == 0`）
- [x] 诊断新增 `systemCursorSuppressed` / `systemCursorFailures` / `systemCursorRequests` / `systemCursorReasserts` / `cursorManagerAlive`
- [x] **10 项插件生命周期门禁**（`parity/plugin-lifecycle.mjs`，用**真实 Cordis + 真实 SessionStore** 跑 `turn/end`）：
      挂载 host 平面服务 → 建一个 bare session（与 agent loop 同路径）→ append 真实 `turn/end` → 断言 `releaseOverlay` 被调用；
      同时**直接断言根因**：preset 作用域的监听器永远收不到该事件（untagged 收得到、tagged 被排除）；
      并覆盖跨会话安全（别的 session 结束 turn 不得动本会话的覆盖层）与 `session/disposed` 清理
      运行方式：`cd <harness>; node --import tsx/esm <repo>\parity\plugin-lifecycle.mjs`（peer 依赖由 checkout 的 tsx 解析，与宿主运行时一致）
- [ ] 待办：插件侧修复需重启 DSH 后才在 GUI 里生效（helper 侧已全量验证）

## 4. 提示词与安全（P4）

- [x] 三份官方文档与官方**逐字节相同**（`Get-FileHash` 比对通过），存放于 `helper-rs/assets/prompts/`
- [x] helper `prompt` RPC 常驻段 = **10,051 字符（~2,513 tokens）**，含 `Non-negotiable Windows Automation Safety` / `## Recovery` / `## Interrupted turns`
- [x] plugin `computerUsePrompt()` 常驻段 = **10,057 字符**，与 helper 同源
- [x] **按官方架构拆分为「常驻 + 按需」**：三份官方文档移入 skill 的 `references/`，模型需要时再读
      （此前无条件注入 36K 字符 / ~9,030 tokens，是回归；现已降到 ~2,513 tokens，**−72%**）
- [x] 三份文档在 helper 资产与 skill 包中**字节相同**（`test_reference_documents_are_bundled_into_the_skill` 断言）
- [x] 常驻段体积门禁 `test_always_on_prompt_stays_small`（< 12,000 字符且仍含 Safety 块与引用指针）
- [x] 单测钉死：**不含** `observation expired` / `default 15s` / `Stale/TTL` / `Do not run pwsh, OCR, PrintWindow`
- [x] 单测钉死：**含**官方 staleness 规则 `valid only for the observation that produced them`
- [x] **官方 guidance 逐条覆盖率 = 100%**：92/92 条指令有关键词对应，12 条 node_repl 专有项由 D1 形态替代
      `python parity/check_guidance_coverage.py` → `gaps: 0`
- [x] 覆盖率已变成回归门禁（`test_every_official_guidance_instruction_is_covered` 调用同一脚本并要求 gaps == 0）
- [x] 覆盖率度量过程补上 4 条真实缺失语义：list_windows 恢复、type_text 字面量、scroll 坐标语义、优先取用可见结果
- [x] `skills/computer-use/SKILL.md` 按官方结构重写并同步到用户预设
- [x] Windows 键禁令在代码层强制：`policy.rs::deny_press_key` + 别名表

## 5. 生命周期（P5）

- [x] sidecar `unref` + `process.once('exit', kill)`（不留孤儿 helper）
- [x] 超时默认**杀进程并拒绝全部在途**；`preserveHelperOnTimeout` 可关
- [x] 预算回到官方 **10s / launch_app 15s**（`index.js` 可配）
- [x] `exit 130` → 官方 `USER_INTERRUPT_MESSAGE` 文案
- [x] turn key 变化 → 先发 `end_turn`（官方 `#ensureTurn`）
- [x] helper 侧 `end_turn` 重置本 turn 状态，不再永久封死（多 turn 可用）
- [x] 物理 Esc 被 hook 吞掉（不再穿透到被自动化的 App）→ 写 interrupt marker → `exit(130)`
- [x] 90s 空闲自杀改为**默认关闭**（`DSH_COMPUTER_USE_IDLE_EXIT_MS`）
- [x] `--previous-notify` / notify-hook 链（`notify::restore_previous_notify`）

## 6. 浏览器（P6）

- [x] 命令表 **57 → 76**，`navigate_tab_url`（官方 `Tab.goto`）不再缺失
- [x] 82 条官方命令真实 payload schema（`browser_schemas.py`）
- [x] 实测：`create_tab` 4 参数 / `tab_ax_action` required `[tab_id, action]` / `mark_tab` 恢复 `handoff|deliverable` / `playwright_locator_click` required `[tab_id, selector]`
- [x] `browser_setup` 补 `undocumentedApiMembers` / `excludedDocumentation`
- [x] `BrowserUseSecurityError`：15 reason + `decision_source` + `retryable` + 两条逐字 wrapper
- [x] 同意文案：origin / history / upload / download / full-CDP（`riskLevel: high`）
- [x] `deny_url` 的 javascript:/vbscript:/ms-appx: 与锁屏拒绝改走安全错误分类
- [x] **11 项安全检查全集 + 3 种安全模式**（`browser_checks.py`）：check id ↔ 遥测 permission name 全表、两张绕过表、逐字拒绝句、同意文案映射
- [x] 门禁接线：`tab_goto` 走官方顺序 **URL 策略 → site-status → origin 同意**
- [x] `BROWSER_USE_SECURITY_MODE` 驱动策略；未知模式 `ValueError`
- [x] 实测（`parity/check_checks.py`）：严格模式 7 个门禁全部拒绝且 reason/retryable 正确；批准 origin 后放行；同源素材静默放行
- [ ] **未做**：`webmcp-tool-call` 页面漂移检测（需真实标签页事件）、`automated-safety-precheck`（GaaS 专用，DSH 不部署）

## 7. 实机验收（P7）

> **桌面已可用**（早先的锁屏记录保留在下方，作为 `require_unlocked()` 的证据）。
> **全部自动化实机项已通过**：`pwsh -File parity/verify-all.ps1` → 11/11 PASS，
> 覆盖光标运动/落位/像素可见性、截图新鲜度、药丸两条渲染路径。
> **交互式三项（Esc / 人机输入 / 审批）已全部自动化并通过**（§3c + `verify-all.ps1`）。
> 另外已用真实 helper 跑通：13 方法、`element_index` 点击、`set_value`、越界/非目标拒绝、
> 锁屏文案。仍**只**剩需要人的手才能触发的项：物理 Esc、手动点击造成的人机输入、
> `launch_app` 审批 UI、录屏观感对比。

> **历史记录（当时的锁屏诊断）**：桌面处于**锁屏**状态。
>
> ```text
> GetForegroundWindow() = 7471846 → LockApp（Windows 默认锁屏界面 / Windows.UI.Core.CoreWindow）
> WTSGetActiveConsoleSessionId() = 1    当前进程 session = 1    connect state = 0 (Active)
> win station = Console                 session user = %USERNAME%
> input desktop name = Default          ← 现代 Windows 锁屏的输入桌面名仍是 Default
> ```
>
> `require_unlocked()` 因此返回官方文案
> `Windows desktop is locked (input desktop is LockApp); unlock before using computer-use`。
> 这与官方 guidance「锁屏时立即停止并请用户解锁，不要试图通过 LockApp 交互」一致，**不是回归**。
>
> **前置风险已排除**：本机 session 1 是 Active 的 Console 会话、用户已登录，
> 所以解锁后必然出现前台窗口，下方验收序列一定可执行（已用 WTS API 核实，非假设）。

解锁后按序执行：

```powershell
# 0) 先确认有前台窗口
pwsh -NoProfile -File <repo>\parity\probe-fg.ps1   # 期望 hwnd != 0

# 1) AX diff 端到端 + 截图可见性
node <repo>\parity\smoke-axdiff.mjs
#    期望：call 2 全量树 → call 3 no accessibility-tree change 或 diff
#          call 4 (disableDiffing) 全量树 → call 5 只截图 → call 6 全量树

# 2) 光标可见性：让模型读一张自己截的图，图里应能看到假光标   [x] 已用像素扫描验证
#    node parity/cursor-trace.mjs ; pwsh -File parity/lag-scan.ps1
# 3) 光标运动观感：录屏与本机官方 exe 并排对比（曲线、46° 外凸、按压态）
# 4) Esc：物理按 Esc → 调用报官方中断文案，后续调用被拒
# 5) 人机输入：手动点目标窗口 → 下一次输入报 user input was detected …
# 6) launch_app 审批：批准 / 拒绝两条路径文案正确
```

## 7b. 第 16 轮：`list_apps` 传输超时（用户实机报告）

> 用户会话 `3e827c8a`（19:27，已重启的新插件 + 新 helper，health 里 `overlay.captureExclusion=mask`）：
> 3 次 `list_apps` 全部在 **10.02 / 10.07 / 10.07 s** 被传输层判超时，而 `computer_use_health` 0.57 s、
> `list_windows` **0.16 s**、`computer_use_experience` 0.01 s 全部正常 —— helper 活着、读得到 stdin，
> 只有 `list_apps` 不作为。超时按官方语义会**杀掉 helper**，所以三连超时同时丢掉了热目录缓存。
> （另外那次会话里 overlay 线程从未启动过：`commands: []`、`pumpIters: 0`，药丸的遮蔽/重建代码根本没参与。）

本机复现（同一台机器、同一条插件路径 `Sidecar`，冷/热缓存都测）：

| 场景 | `list_apps` 墙钟 | 目录来源 | `signalsMs` | `mergeMs` |
|---|---|---|---|---|
| 磁盘缓存可用（新进程首次） | 461 ms | disk-fresh | 135 | **324** |
| 同进程再次调用 | 166-184 ms | memory-fresh | 129-137 | **36** |
| 完全无缓存 | 202-547 ms（目录空，只返回 8 个窗口条目） | none | 118-145 | 30-419 |
| 后台重建（不阻塞作答） | **3.73 s** | — | — | — |

重建阶段耗时：shortcut-pair 3 / start-menu-user 634 / start-menu-machine 1636 /
windows-apps-aliases 13 / **apps-folder 1332** / 注册表各项 1-38 ms。

定位：`mergeMs` 几乎全部花在**每个已安装应用解析一次 PE ProductName**
（`prefer_product_name` → `policy::product_name`，本机 751 个应用 = 751 次打开可执行文件），
而它每次观察都会重做。文件系统忙、或杀毒软件逐个扫描被打开的文件（本机装了 Kaspersky）时，
这一步会被拉长到数秒以上 —— 与「只有 `list_apps` 超时、`list_windows` 0.16 s」的形态吻合。

- [x] **ProductName 进程内记忆化**（`PRODUCT_NAMES`，目录重建完成时失效）：`mergeMs` 324 ms → **36 ms**，
      每次调用不再打开 751 个可执行文件
- [x] **`listAppsTimeoutMs`（DSH 扩展，默认 30 s）**：目录是唯一「作答前要干活」的方法；为一个慢但健康的
      目录杀掉 helper，只会让下一次尝试也变冷。其余方法仍是官方 10 s（`launch_app` 15 s）
- [x] **慢请求日志** `%LOCALAPPDATA%\computer-use-app-catalog\slow-requests.log`：记录超过
      `DSH_CU_SLOW_REQUEST_MS`（默认 1 s，0 = 全记）的每个请求 —— 方法、耗时、`appCatalog` 计时与重建阶段。
      传输超时会把 helper 连同进程内诊断一起杀掉，这份文件是唯一能活下来的证据
- [x] `appCatalog` 诊断（`cacheSource/installedMs/signalsMs/mergeMs/rebuildMs/rebuilds/rebuildStage(s)`）
      进 `diagnostic_state`，并随 `computer_use_health` 的 `overlay` 合并一起可见
- [x] 门禁 `tests/contracts.test.mjs`「list_apps gets a catalog-sized transport budget」：
      默认 30 s、`launch_app` 仍 15 s、其余仍 10 s、helper 侧日志代码必须存在

遗留：三连超时的**直接**触发因素尚未复现（本机同样调用 0.2-0.5 s）。下一次复现时
`slow-requests.log` 会直接给出当时的方法耗时与目录阶段，不必再靠推测。

## 7c. 第 17 轮：`list_apps` 真的卡了 31 秒，以及"自动退出"的真相（用户实机）

> 用户会话 `b9bdf958`（19:45，重启后的新插件/helper）：`computer_use_health` 0.34 s、`skill` 立即，
> 然后 `list_apps` 被 **harness 的 25 s 工具预算**中止（`ToolTimeoutError TOOL_TIMEOUT`），紧接着
> `list_windows` 返回 **"Computer Use was stopped by the user with the physical Escape key"**，
> 模型据此结束回合 —— 用户的原话是「好像自动退出了，我啥都没点」。

**证据（上一轮加的慢请求日志抓到了现场）**：

```json
{"appCatalog":{"apps":751,"cacheSource":"disk-fresh","installedMs":181,"listMs":31466,"mergeMs":31285,
 "signalsMs":171,"rebuilds":0,"rebuildStage":"idle"},"at":1789472780,"elapsedMs":31474,
 "label":"call list_apps","processId":133216}
```

即：`list_apps` 在 helper 里跑了 **31.47 s**，其中 `mergeMs=31285` —— 目录本身只花 181 ms。
`mergeMs` 的主体是**每个已安装应用解析一次 PE `ProductName`**（本机 751 次打开可执行文件），
在这台机器上（Kaspersky 逐个扫描打开的文件）要 31 s，而本机热缓存下只要 324 ms。
上一轮的"记忆化"只能救第二次调用，救不了每个新 helper 的**第一次**调用 —— 那次照样 31 s。

**第二个 bug（"自动退出"的直接原因）**：harness 25 s 预算到点后会**中止工具调用**，插件的中止
路径发的是 `interrupt` RPC，而 helper 的 `interrupt` 会 `interrupt::trip()` → `STOPPED=true` latch。
于是**同一进程**里后续每个 CU 调用都报官方的「用户按了物理 Esc」文案，模型按契约停止整个回合。
（`cancel_work` 的注释早就写了"RPC timeout / cancel: do not treat as physical Escape"，只是中止路径没走它。）

修复与验证：

- [x] **把 ProductName 解析搬到后台重建线程**：`ShellApp.product_name` 进目录缓存，`installed_display_name`
      请求路径**永不打开可执行文件**。验证：`list_apps` 186-202 ms、`mergeMs` **38-39 ms**（旧逻辑同机 324 ms / 该机 31.5 s），
      754 条目与显示名不变
- [x] **`listAppsTimeoutMs` 默认 20 s（< harness 的 25 s）**，且**逐字采用**不夹到 10 s：先于 harness 超时，
      得到的是干净的传输错误而不是"中止 → latch"
- [x] **`keepAlive`**：`list_apps` 超时不再杀 helper。验证：1 ms 预算下请求被拒，但 `primary.alive === true`
      且同一个 helper 仍能回答 `health`（旧行为会杀掉它并丢掉热目录）
- [x] **中止路径改发 `cancel`**（`cancel_work`：只隐藏覆盖层），不再 latch 成"用户停止"；
      宿主 Stop 钩子的 `interrupt()` 仍保留 latch 语义（那才是真的用户停止）
- [x] 门禁：契约 34/34，新增「budget below the harness budget」「abort cancels instead of latching」
      「请求路径不得再用 `prefer_product_name(&shell.display_name…)`」三条
- [ ] 待实机复验：用户重启 DSH 后再跑一次微信任务（预期：`list_apps` 亚秒返回，药丸常驻，不再"自动退出"）

## 8. 剩余工作（不阻塞已完成的验收项）

- [x] P7 自动化实机项（`parity/verify-all.ps1` 11/11 PASS）
- [ ] P6 其余安全检查项（site-status / page-asset / webmcp-tool-call 等 8 项）
- [ ] `launch_app` 批准 UI 的友好 `displayName`（当前用 app id）
- [x] 官方 AX 树 element index 承载格式的 golden sample（风险 R8）—— 已用官方 helper 本体逐字取得并修正，见 §3
- [ ] 动画时长 tick 的实机反推（风险 R1：静态提取 0 命中，走录屏）
