---
paths:
  - "scripts/**/*.ps1"
  - "*.ps1"
---

# PowerShell Rules
> 🥇 Operational | Load: on PowerShell script execution | Scope: all .ps1 scripts | Overrides: N/A

- ErrorActionPreference = "Continue" or "Stop" explicitly set at script top. No implicit defaults.
- All paths absolute. Use `$env:USERPROFILE` or `$PSScriptRoot`, never relative paths.
- Native exe calls: check `$LASTEXITCODE` immediately after `& cmd`.
- Avoid `New-Item -Force` on files — it truncates. Use `if (-not (Test-Path)) { New-Item }`.
- `try/catch` requires `-ErrorAction Stop` on the cmdlet, or it won't catch.
- No `Write-Host` in hook scripts — use `Write-Output` for hook-visible output.

## Production-Grade Rules (肌肉记忆 — 2026-06-25 审查教训)

### 1. 原子写入
**Never** `Set-Content $target` directly on critical files.
**Always** `Set-Content $tmp; Move-Item -Force $tmp $target`.
Crash mid-write = corrupted file. Applies to: MEMORY.md, settings.json, state files, gate files.

### 2. 工具检测
**Never** hardcode `python3` or `python`.
**Always** detect: `$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }`.

### 3. 诚实架构
Hook = 确定性检测 + 信号发射。LLM = 内容理解 + 合成。
**Never** 在 PowerShell 里硬编码假数据（如 principle map）。
做不了就说做不了，发信号让能做的人做。

### 4. 无硬编码用户/路径
**Never** 硬编码 `z1439`、`C--Users-z1439--claude` 等用户名。
**Always** 用 `$env:USERPROFILE` 或从 git remote / filesystem 动态获取。
原则：脚本必须能跑在别人机器上。

### 5. 静默失败禁止
`2>$null` 只用于已知可忽略的操作（如 `git status` 在非 git 目录）。
**Never** `$ErrorActionPreference = "SilentlyContinue"` 全局。
错误要么处理，要么传播。吞掉 = 埋雷。

### 6. 并发安全
修改状态文件（gate、distill_state、memory_scores）→ 加锁或接受覆盖。
同一 hook 可被多次触发（多个 matcher），脚本必须幂等。

### 7. 写入后验证
写完关键文件后立即 `Test-Path` + 检查非空。
不假设写成功。
