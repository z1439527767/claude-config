# CLAUDE.local.md — Personal overrides (gitignored, not shared)

## 偏好
- PowerShell for Windows, Bash for POSIX
- 中文回复，代码/文档用英文
- 直接改文件，少解释
- 80% 方案现在 > 100% 方案以后

## 当前
- ~/.claude 框架 v2 运行中（进化管线已删除，能力桥接已部署）
- 上次任务：项目能力桥接部署 + KG 巩固 + 技术债清零

## 最近发现
- 2026-06-26: 线性注意力无法架构级解决 → 三层围堵（位置/外部检测/文件物证）
- 2026-06-26: 只加不删原则 — 项目文件只能新增不能修改已有
- 2026-06-26: `New-Guid` 不是有效 cmdlet → 用 `[Guid]::NewGuid()`
- 2026-06-26: `ConvertFrom-Json` 返回 PSObject 不是 hashtable → 不能 `$obj[key]` 索引
- 2026-06-25: PowerShell 脚本避坑：`??` 用 if/else；管道到 native exe 丢 CJK；`<` 是 PS7 保留字
- 2026-06-25: 学到的必须立刻写入自身配置，否则等于没学
