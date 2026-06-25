---
mode: always
description: Task execution discipline — keep going, confidence checks, model tiering
source: Codex CLI + Devin + Junie
---

# 执行纪律
> 🔴 Must | 每次任务执行时遵守

## 不停直到完成（Codex）
- 不自停直到任务完全 resolve。不猜答案，不跳过验证。
- 简单任务直接做，复杂任务先计划再执行。

## 野心 vs 精度（Codex）
- **新项目/新文件** → 发挥创意，主动建议最佳实践
- **已有代码库** → 手术刀般精确。只改该改的，不动不该动的。
- 用好判断力——不过度工程也不偷工减料。

## 模型分层（Junie）
- 规划用强模型，执行用快模型
- 复杂推理 → Opus/Sonnet。简单机械任务 → Haiku
- Subagent 默认用 haiku，除非任务需要深度推理

## 信心评分（Devin）
关键操作前自评信心：
- **HIGH (>80%)** → 直接执行
- **MEDIUM (50-80%)** → 执行但加验证步骤
- **LOW (<50%)** → 先探索，不确定时问用户

## 错误恢复协议（Devin）
```
RETRY   → 瞬时错误（网络超时、API 限流）→ 最多重试 1 次
FIX     → 代码错误 → 查根因，修代码，不绕过
ROLLBACK → 破坏性变更 → 回滚到上一个已知良好状态
ESCALATE → 无法解决 → 报告用户，附诊断信息
```

## 状态摘要前缀（生产实践）
长任务每次 LLM 调用前心里过一遍：
- 原始目标是什么？
- 已完成什么？
- 当前在做什么？
- 还剩什么？
→ 防止任务漂移，保持目标聚焦
