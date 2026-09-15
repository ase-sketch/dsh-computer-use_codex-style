
---

## 附录 F — 第 6 轮：P7 前置风险澄清 + P4 覆盖率收口

> 本轮结束时：`cargo test --release` **81 passed / 0 failed**；Python `pytest` **193 passed / 0 failed**。

### F.1 P7 前置风险已澄清（此前是假设，现在是证据）

前五轮我一直向用户说「解锁桌面后就能验收」，但**从未验证解锁后是否真的会出现前台窗口**。
如果这台机器是断连会话或无控制台会话，那 P7 将永远无法验收 —— 交付物就成为无法兑现的承诺。本轮把这个风险查清了：

```
WTSGetActiveConsoleSessionId() = 1
当前进程 session              = 1
session 1 connect state       = 0 (Active)
win station name              = Console
session user                  = %USERNAME%
```

**结论：session 1 是 Active 的 Console 会话，用户已登录，且它就是活动控制台会话。**
所以「解锁后会得到前台窗口」这个前提成立，前面的验收指引是可靠的 —— 不是空头支票。

顺带确认了两件事：
1. 之前看到的 `GetForegroundWindow() = 0` 是**锁屏过渡态的瞬时空值**；现在锁屏窗口稳定在前台时返回的是 `LockApp` 的 `Windows.UI.Core.CoreWindow`。第 4 轮补的 `LockApp` 检测正好覆盖这个真实状态。
2. WGC 截图与 AX 路径**无法在锁屏下单独演练** —— 唯一无门禁的读取方法是 `list_windows`/`list_apps`/`get_window`，而它们都只走 EnumWindows，不碰 capture。这是硬约束，不是可以绕过的实现细节。

### F.2 P4 覆盖率收口（用度量代替断言）

新增 `parity/check_guidance_coverage.py`：把官方 `guidance.md` 的每一条指令归约为**特征关键词集合**
（剔除停用词、剔除 `node_repl` 专有词汇），再要求 DSH 提示词包**全部包含**。

度量方式刻意做成**语义而非字面**：改写能过、丢指令不能过。第一版用「第一句精确匹配」，
结果把我自己语义相同的改写全判为缺失 —— 那是在测断句而不是测内容，已改正。

**结果**：

```
instructions checked        : 92
covered                     : 92
gaps                        : 0
replaced by D1 (node_repl)  : 12
bundle chars                : 36123
```

度量过程还**发现并补上了 4 条真实缺失的语义**（此前只有官方原文在 `guidance.md` 里、DSH 段没有对应表述）：

| 补入 DSH 段的指令 | 原文要点 |
|---|---|
| `list_windows()` 恢复 | 「用 `list_windows()` 检查当前窗口或恢复已知运行中的应用；App 不在 `list_apps` 里时用显式 `.exe` 路径启动，刷新后**只在过滤结果恰好一个窗口时**继续」 |
| `type_text` 字面量语义 | 「`type_text` 发送**字面文本**；输入前立即复核焦点；控制键用 `press_key`，**不要把控制字符嵌进字符串**」 |
| `scroll` 坐标语义 | 「`scroll` 从窗口相对坐标注入滚动：`x`/`y` + `scrollX`/`scrollY`，负值方向语义；需要特定面板获得焦点时**先用坐标点它再滚**」 |
| 直接取用可见结果 | 「优先使用当前状态里**已经可见**的直接结果，而不是打开更宽的中间 UI（如 'Show All'）；结果一旦可见就停止探索并回答」 |

### F.3 覆盖率已变成回归门禁

`tests/test_parity.py` 新增 `test_every_official_guidance_instruction_is_covered`：它**调用同一个脚本**并要求
`gaps == 0`。也就是说，今后任何人删掉或软化一条官方指令，测试立刻失败。

至此 parity 测试共 **12 条**，其中 3 条直接跑子进程（真实 helper stdio、覆盖率脚本），其余为契约断言。

### F.4 提示词体量变化

| 通道 | 起始 | 现在 |
|---|---|---|
| helper `prompt` RPC | 15,145 字符 | **36,141 字符** |
| DSH plugin system prompt | ~2,000 字符 | **36,136 字符** |

两者同源（同一组 `assets/prompts/*.md`），差异仅为换行拼接方式。

### F.5 P7 状态

不变：桌面锁屏。但**前置风险已消除** —— 解锁后必然可用，执行 `CHECKLIST.md` 第 7 节即可。
