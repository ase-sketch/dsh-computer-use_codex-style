
---

## 附录 G — 第 7 轮：修正一处我自己引入的性能回归（提示词体积）

> 本轮结束时：`cargo test --release` **82 passed / 0 failed**；Python `pytest` **195 passed / 0 failed**。

### G.1 问题：我把系统提示从 2K 字符涨到 36K，且每轮无条件注入

P4 接线时我把官方三份文档（`guidance.md` / `api.md` / `confirmations.md`）全部 `include_str!` 进 `native_prompt()`，
又让 DSH plugin 把同一份内容塞进 systemPrompt section。实测代价：

| 文件 | 字符 | ~tokens |
|---|---|---|
| `dsh-header.md` | 9,572 | 2,393 |
| `guidance.md` | 13,907 | 3,477 |
| `api.md` | 8,028 | 2,007 |
| `confirmations.md` | 4,613 | 1,153 |
| **合计（每轮注入）** | **36,120** | **~9,030** |

而**官方不是这么做的**：官方把 `SKILL.md` 作为 skill（按需加载），`guidance.md`/`api.md`/`confirmations.md`
作为 skill 目录下的**引用文档**（`../../docs/*.md`），让模型**需要时才读**。我把「按需」做成了「无条件」。

这是一处**真实的性能回归**：每轮多 ~9k tokens，且与官方架构背离。

### G.2 修正：按官方架构拆分为「常驻 + 按需」

| 内容 | 去向 | 理由 |
|---|---|---|
| session contract / 两段式循环 / staleness 规则 / Recovery / Interrupted / **完整 Safety 禁令块** | **常驻系统提示** | 安全拒绝必须无条件在场；这些是每次都要遵守的行为约束 |
| `guidance.md` / `api.md` / `confirmations.md` | **skill 的 `references/`** | 官方同款按需读取；查签名、查确认策略时再读 |
| `SKILL.md` | skill 正文，按官方结构写明四个 `references/*` 的用途 | 官方 SKILL.md 就是这么指向 docs 的 |

三份文档现在**同时存在于 helper 资产与 skill 包**，并有测试断言两者字节相同（防漂移）。
同步到了三个 skill 根：插件目录、用户预设目录、`~/.dsh/skills`。

### G.3 效果

| 指标 | 修正前 | 修正后 | 变化 |
|---|---|---|---|
| helper `prompt` RPC | 36,141 字符（~9,035 tok） | **10,051 字符（~2,513 tok）** | **−72%** |
| DSH plugin system prompt | 36,136 字符（~9,034 tok） | **10,057 字符（~2,514 tok）** | **−72%** |
| 官方 guidance 覆盖率 | 92/92 | **92/92** | 不变 |
| Safety / Recovery / Interrupted 在场 | ✅ | ✅ | 不变 |
| 指向三份引用文档 | ✅ | ✅ | 不变 |

新增两条门禁：

- `test_always_on_prompt_stays_small`：常驻段必须 < 12,000 字符，且仍含 Safety 块与引用指针
- `test_reference_documents_are_bundled_into_the_skill`：三份文档必须在 skill 的 `references/` 里，
  且与 helper 资产**字节相同**；`SKILL.md` 必须指向它们

覆盖率检查器也改为**对内容去重**后统计（此前把资产与 skill 里的同一份文件重复计数，报出 82,055 的虚高值，
真实可读文本为 **45,452 字符**）。

### G.4 度量口径说明

「可达文本」= 常驻 10,051 + 三份引用文档 26,548 + SKILL 8,851 = **45,450 字符**，
既等于官方模型可见的完整材料，又不必每轮付费。每轮实际成本回到 2.5k tokens 量级，与官方 skill-body 预算相当。

### G.5 P7 状态

不变：桌面锁屏。
