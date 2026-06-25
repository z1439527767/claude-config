---
mode: always
description: Tool selection + ambition vs precision + model tiering
source: Codex CLI + Junie
---
# 工具选择规则（含 Codex 野心vs精度）
> 🔴 Must | 每次调工具前过一遍

## 野心 vs 精度（Codex + 全平台共识）
- **新项目/新文件** → 发挥创意，主动建议最佳实践，展示可能性
- **已有代码库** → 手术刀般精确。只改该改的，不动不该动的。不改文件名/变量名除非必要。
- **用好判断力** — 不过度工程也不偷工减料。做刚好够用的方案。

## 禁止混用
- Bash 不跑 `find/grep/cat/head/tail/sed/awk/echo` → 用 Glob/Grep/Read 专用工具
- PowerShell 不跑 `Get-ChildItem -Recurse` (搜索) → 用 Glob
- PowerShell 不跑 `Select-String` (内容搜索) → 用 Grep
- PowerShell 不跑 `Get-Content` (读文件) → 用 Read
- PowerShell 不跑 `Set-Content/Out-File` (写文件) → 用 Write

## 选择顺序
1. 专用工具优先（Glob > Grep > Read > Edit > Write）
2. 文件操作读不通再试 shell
3. 复杂逻辑（条件/循环/管道）→ PowerShell（Windows）或 Bash（POSIX）
4. 多个独立操作 → 并行工具调用，不串行

## 模型分层（Junie）
- 规划/深度推理 → 强模型。简单机械任务 → Haiku subagent。
- 重要改动 → 跨模型审查（主 agent 写，haiku subagent 独立审）

## 能并行不串行
- 两个及以上互不依赖的工具调用 → 同一轮发出
- 不要一个等一个，除非后者依赖前者的输出

## 验证
- 每次工具调用后检查 exit code
- Bash: 非零 = 失败
- PowerShell: `$LASTEXITCODE` 或 try/catch
- 不确定时再查一次确认
