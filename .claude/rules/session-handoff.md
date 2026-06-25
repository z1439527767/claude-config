# 会话交接规则
> 🟢 Guidance | 跨会话保留什么，清理什么

## 保留（L1 运行层）
- handoff.md：当前任务状态、未完成的工作、下一步
- loop_state.json：循环任务的进度
- session-env/：跨会话环境变量

## 清理（L3 即时层）
- 临时测试文件
- 中间构建产物
- 过期的性能日志

## 启动检查
- SessionStart hook 跑完后：
  1. 读 handoff.md（如有）→ 恢复上下文
  2. 读 session-env/user-lang.txt → 知道用户语言
  3. 读 .last-cleanup → 上次清理时间，超过 24h 清理

## 结束前
- 未完成的任务 → 写 handoff.md
- 循环任务 → 更新 loop_state.json
- 新学到的东西 → 写记忆/规则
- git snapshot（SessionEnd hook 自动处理）
