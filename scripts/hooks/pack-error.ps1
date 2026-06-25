# pack-error.ps1 — PostToolUseFailure: auto-pack error context using data-pack
param()
$ErrorActionPreference = "Continue"

$toolName = $env:CLAUDE_TOOL_NAME
$error = $env:CLAUDE_TOOL_ERROR

if (-not $error -or $error.Length -lt 5) { exit 0 }

$packInput = @"
Tool: $toolName
Error: $error
Context: Failed tool call at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Root cause: TBD — investigate
Fix: TBD
"@

$packInput | python3 "$env:USERPROFILE\.claude\scripts\data-pack.py" --type error --source "hook/$toolName" 2>$null
exit 0
