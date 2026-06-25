# 进化策略规则
> 🔴 Must | 蒸馏自 GenericAgent + Evolver + SIA

## 策略预设
- `balanced` — 均衡：修复+优化+创新各 1/3
- `harden` — 巩固：80% 修复已知问题，20% 优化
- `innovate` — 创新：50% 新能力，30% 优化，20% 修复
- `repair-only` — 纯修复：100% 修问题

当前策略：读取 `~/.claude/session-env/evolve-strategy.txt`，默认 `balanced`

## 进化闭环
New Task → Autonomous Explore → Crystallize into Skill → Direct Recall

## 进化约束
- 只读分析（不直接改源码，输出建议让 confirm 后再改）
- 每次进化记录写到 `~/.claude/.claude/evolution/` 目录
- 版本化：`evolve_YYYYMMDD_HHMMSS.json` 不可变
- 同错 2 次 → 停止进化，进入诊断模式
- 进化门控：只在实际修改时计数，观察不算

## 验证安全
- 命令执行：只允许预定义工具（python, pwsh, git, node），禁止 shell 操作符注入
- 超时：每次进化操作 10s 上限
- 回滚：进化失败自动恢复上一个已知良好的配置快照
