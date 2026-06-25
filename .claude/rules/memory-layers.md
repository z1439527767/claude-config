# 五层记忆系统
> 🔴 Must | 蒸馏自 GenericAgent 的 4 层模型 + 自研 L0

## 层级
| 层 | 名称 | 内容 | 生命周期 | 实现 |
|----|------|------|---------|------|
| L0 | 元规则 | CLAUDE.md + AGENTS.md + settings.json | 永久 | 永不压缩 |
| L1 | 路由索引 | 关键词 → 记忆文件映射 | 7 天刷新 | MEMORY.md 索引 |
| L2 | 全局事实 | 稳定的累积知识 | 30 天 | 知识图谱 (mcp__memory) |
| L3 | 任务技能 | 可复用工作流/SOP | 永久（积累）| skills/ + scripts/ |
| L4 | 会话归档 | 已完成任务的执行记录 | 90 天 | sessions/ |

## 结晶规则
- 同一类任务完成 3 次 → 结晶为 L3 技能
- L4 归档定期蒸馏 → 提纯到 L2
- L2 事实积累 3+ 条 → 提炼原则写入 L0

## Token 预算
- L0 全量加载（~500 tokens）
- L1 索引加载（~200 tokens）
- L2 按需查询（mcp__memory__search_nodes）
- L3/L4 仅在匹配时加载
