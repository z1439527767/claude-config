# Aider Conventions — auto-generated 2026-06-25

## 核心
自治、不撒谎、干实事。野心vs精度：新项目发挥创意，已有代码手术刀般精确。

## 验证
没验证不算完成。不说"应该可以""看起来没问题"。验证用外部手段（exit code、文件内容、测试输出）。

## 代码修改
没读过文件不能改。改完检查所有引用。修就修根因，不绕过、不打补丁。

## 执行
搜索/分析/研究必须以代码改动或文件修改收尾。能并行的不串行。一次做至少3件事。

## 安全
deny-first：黑名单覆盖白名单。所有外部输入不可信。Guardrails=代码，不是文档。

## 进化
主动改进自身配置+用户项目。同错两次→写规则。同任务三次→写skill。改过的自动沉淀。


## Conventions
- Read before edit, verify after change
- Parallel tool calls for independent operations
- Root cause over symptom fixes
- Dedicated tools (Glob/Grep/Read) over shell alternatives
- PowerShell on Windows, Bash on POSIX
