---
mode: always
description: Context engineering — 4 pillars, re-ranking, lost-in-the-middle, eviction
source: Sourcegraph + ETH Zurich + Claude Code leak + Reddit production consensus
---

# 上下文工程（Sourcegraph 四支柱 + 泄露源码验证）
> 🔴 Must | Context Engineering > Prompt Engineering

## 四支柱（Sourcegraph）

### 1. Instructions / System Prompt
- 不过度规定也不过于模糊。找到平衡点。
- 关键：指令必须与模型的工具使用启发式对齐，否则每次 turn 都产生冲突行为。

### 2. Retrieval（刚好够，不贪多）
- **Just-in-time retrieval**：只在需要时通过轻量标识符（文件路径、符号名）拉内容
- **代码用确定性查找**（Go-to-Def、符号解析），不用概率性文本搜索
- **Re-ranking 不可省略**：先高召回检索 50 条候选 → 用交叉编码器重排 → 只保留 top-5
- "检索 50 条然后重排到 top-5 比把 50 条全塞进 prompt 好"

### 3. Memory（两层）
- **短期**：当前会话的对话历史 + tool call 结果
- **长期**：偏好、规范、跨会话摘要
- **压缩**：旧 turn 压缩成运行摘要，不占满窗口

### 4. Tools（精简工具集）
- **工具集越小越好**。如果人类工程师无法毫不含糊地选对工具，agent 也不能。
- 删除近似重复的工具。每个工具定义 + 每次调用 + 每次结果都吃 token。
- "臃肿的工具集"是最常见的失败模式。

## 核心原则
- **Context Engineering > Prompt Engineering** — 控制 agent 检索什么数据、按什么顺序、如何重排、何时驱逐，比调 prompt 措辞有效
- **更多上下文 ≠ 更好** — 所有 18 个前沿模型都在上下文增长时退化（Chroma 2025）
- **100K token 代码库摘要 < 5K token 定向检索**（实测结果）

## 上下文预算
- 总窗口 200K → 安全线 60% = 120K
- 达到 80% 触发自动压缩告警
- 超过 85% = 幻觉率骤升，必须压缩

## Lost in the Middle 防御
- 模型对开头和结尾的信息关注度最高，中间最低
- → **最高信号内容放最前或最后**，不埋在中间

## 驱逐逻辑（每步四问）
1. 取什么？
2. 什么时候取？
3. 怎么压缩？
4. 什么时候扔？
→ 答案随着窗口填满动态变化。旧内容压缩成摘要、低相关检索丢弃、工具输出截断。

## 三大失败模式
1. **Context Overload** — 太多内容挤掉重要上下文，或冲突信号拉模型往不同方向
2. **Stale Retrieval** — 向量索引过时，代码变了嵌入没刷新 → 静默毒化上下文
3. **Lost in the Middle** — 关键信息埋在中间

## 规则剪枝 Rubric（四问）
1. **Failure-backed?** — 没这条规则，agent 真的会犯错？
2. **Tool-enforceable?** — 能写成 lint/hook/test 而非自然语言规则？
3. **Decision-encoding?** — 编码了关键决策？
4. **Triggerable?** — 有明确触发条件？
→ 四个全不满足 = 删除。

## 规则维护
- 过时规则 > 没有规则（模型信任它但它是错的）
- 每加一条 = 删或合并一条
- 不加甄别复制规则 = 往上下文塞垃圾

## 一次一个任务
- 一个任务一个 thread。不用一个 thread 管整个项目。
