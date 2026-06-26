# pack-error.ps1 — PostToolUseFailure: auto-pack error context using data-pack
param()
$ErrorActionPreference = "Continue"

$toolName = $env:CLAUDE_TOOL_NAME
# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "pack-error" -EntityName "hook-pack-error-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("pack-error executed at $(Get-Date -Format 'o')") -Priority "low"
$error = $env:CLAUDE_TOOL_ERROR

if (-not $error -or $error.Length -lt 5) { exit 0 }

$packInput = @"
Tool: $toolName
Error: $error
Context: Failed tool call at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Root cause: TBD — investigate
Fix: TBD
"@

$packInput | python "$env:USERPROFILE\.claude\scripts\data-pack.py" --type error --source "hook/$toolName" 2>$null
exit 0
