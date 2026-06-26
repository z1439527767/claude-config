# CLAUDE.local.md — Personal overrides (gitignored, not shared)

## 偏好
- PowerShell for Windows, Bash for POSIX
- 中文回复，代码/文档用英文
- 直接改文件，少解释
- 80% 方案现在 > 100% 方案以后

## 当前
- ~/.claude 框架优化进行中
- 上次任务：自托管进化系统部署完成

## 最近发现
- 2026-06-25: PowerShell 脚本避坑：`??` 用 if/else 替代；管道到 native exe 丢 CJK 编码 → 用参数模式；`<` 是 PS7 保留字；`@(a -flag, b -flag)` 是错误数组语法 → 用 `(a -flag), (b -flag)`
- 2026-06-26: `New-Guid` 不是有效 cmdlet → 用 `[Guid]::NewGuid()`。`New-Guid.ToString()` 返回空字符串导致 tmp 文件路径错误
- 2026-06-26: `ConvertFrom-Json` 返回 PSObject 不是 hashtable → 不能 `$obj[key]` 索引。必须遍历 `.PSObject.Properties` 手动转 `@{}
- 2026-06-25: 学到的必须立刻写入自身配置，否则等于没学
- 2026-06-25: Claude 每次响应必然停——Workflow 填补空白，我做编排者
- 2026-06-24: 进化自身 ≠ 动用户项目。只改三个文件。
