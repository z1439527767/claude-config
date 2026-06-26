# precompact-guard.ps1 — PreCompact: preserve core rules + smart compression hint
param()
$ErrorActionPreference = "Continue"
$perfHookName = "precompact-guard"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
$guard = @"
# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "precompact-guard" -EntityName "hook-precompact-guard-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("precompact-guard executed at $(Get-Date -Format 'o')") -Priority "low"
POST-COMPACT RULES STILL ACTIVE:
1. No verification = not done. External evidence only.
2. Do exactly X, don't expand to other tasks.
3. Fix root cause, don't patch symptoms.
4. Self-evolution ≠ modifying user projects.
5. Search/analysis must end with a file change.
6. GitHub search first for config patterns, then web.
7. PreToolUse hooks must have precise matchers.
8. Stop hook {"decision":"block"} is native self-loop.

Session context was compacted. Core constraints survive.
"@
Write-Output $guard
$guard | Set-Content "$env:USERPROFILE\.claude\.claude\post_compact_guard.txt" -Encoding UTF8
Write-PerfLog 0; exit 0
