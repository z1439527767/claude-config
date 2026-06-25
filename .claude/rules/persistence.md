---
mode: always
description: When to write what + pruning rubric (Failure-backed? Tool-enforceable? Decision-encoding? Triggerable?)
source: Reddit/HN production consensus
---
# 沉淀规则：什么时候写什么（含剪枝 Rubric）
> 🟢 Guidance | 做完事别忘了留痕迹

## 写前先剪枝 — 四问 Rubric（生产共识）
对每条要加的规则，先问：
1. **Failure-backed?** — 没这条规则，agent 真的会犯错？
2. **Tool-enforceable?** — 能写成 lint/hook/test 而非自然语言规则？
3. **Decision-encoding?** — 编码了关键决策（技术选型、架构约束）？
4. **Triggerable?** — 有明确触发条件还是永远占着上下文？
→ 四个全不满足 = 不写。能写成代码的不要写规则。

## 维护铁律
- 加一条 → 审视周围内容，删除或合并一条与之相关的
- 过时规则 > 没有规则（模型信任它但它是错的）
- 规则文件 > 200 行必须拆分或删减

## 写记忆（知识图谱）
- 错误发生 → 立即记：时间、上下文、根因
- 新工具/库选型结果 → 记：为什么选 A 不选 B
- 用户偏好变化 → 记：改了什么偏好，为什么
- 成功模式 → 记：做对的事，下次直接复用

## 写规则（CLAUDE.md / AGENTS.md / .claude/rules/）
- 同错两次 → 写规则防止第三次
- 用户纠正行为 → 写规则内化
- 工作流发现 → 写 SOP（如本文件）

## 写工具脚本（~/.claude/scripts/）
- 新装 CLI 工具 → 写 wrapper 脚本
- 重复操作超过 3 次 → 写脚本自动化
- 研究结果 → 写工具落盘

## 写 Skill（.claude/skills/）
- 同一任务完成 3 次 → 结晶为 skill
- 每次用同样的 prompt 纠正同样的 workflow → 该写 skill 了
- 好 skill 候选：log triage、PR review、migration、debug flow

## 不写
- 一次性的临时操作
- 代码库本身能推导的信息（目录结构、git log）
- 纯会话内状态（会自然过期）
