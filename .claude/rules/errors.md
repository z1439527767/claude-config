---
mode: always
description: Error handling with RETRY→FIX→ROLLBACK→ESCALATE protocol
source: Devin + Microsoft SRE
---
# 错误处理链（含 Devin 错误恢复协议）
> 🔴 Must | 遇到错误不跳过，不走捷径

## 错误恢复协议（Devin + 微软 SRE）
```
RETRY    → 瞬时错误（网络超时、API 限流、临时文件锁）→ 最多 1 次
FIX      → 代码错误（语法、逻辑、类型）→ 查根因，修代码，不绕过
ROLLBACK → 破坏性变更（删除数据、不可逆操作）→ 回到上一个已知良好状态
ESCALATE → 无法解决（权限不足、第三方服务宕机、超出能力范围）→ 报告用户附诊断信息
```

## 出错三步（不变）
1. **查记忆** → `mcp__memory__search_nodes` 查同类错误。先查后修。
2. **查代码** → 看报错的代码段。不猜。
3. **修根因** → 不绕过、不打补丁、不 silence 错误。

## 同错两次 = 停
- 同一个错误出现第二次 → 停下来找根因
- 不修症状。两个症状 = 一个根因没修。

## 静默失败禁止
- ErrorActionPreference = "SilentlyContinue" 只用于已知可忽略的操作
- 禁止 `2>$null` 吞掉重要的错误流
- 禁止 try/catch 空 catch 块
