# precompact-guard.ps1 — PreCompact: preserve core rules before context compression
param()

# Write critical constraints to a known location before compaction
# Claude can reference this after context is compressed
$guard = @"
POST-COMPACT RULES STILL ACTIVE:
1. No verification = not done. External evidence only.
2. Do exactly X, don't expand to other tasks.
3. Fix root cause, don't patch symptoms.
4. Self-evolution ≠ modifying user projects.
5. Search/analysis must end with a file change.

Session context was compacted. Core constraints survive.
"@

$guardFile = "$env:USERPROFILE\.claude\.claude\post_compact_guard.txt"
$guard | Set-Content $guardFile -Encoding UTF8

Write-Output $guard
exit 0
