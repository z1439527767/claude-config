# echo-of-prompt.ps1 — UserPromptSubmit: auto-capture task + re-inject every N calls
# No pre-existing file needed — auto-captures from first substantive prompt.
param(
    [string]$prompt = ""
)
$ErrorActionPreference = "Continue"
$perfHookName = "echo-of-prompt"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$taskFile = "$env:USERPROFILE\.claude\.claude\task-context.md"
$stateFile = "$env:USERPROFILE\.claude\.claude\echo_state.json"
$echoInterval = [int]$env:CLAUDE_FOCUS_ECHO_INTERVAL
if ($echoInterval -le 0) { $echoInterval = 12 }

# Track call count
$count = 0; $lastEcho = 0
if (Test-Path $stateFile) {
    try {
        $state = Get-Content $stateFile -Raw | ConvertFrom-Json
        $count = [int]$state.count; $lastEcho = [int]$state.last_echo
    } catch {}
}
$count += 1

# Auto-capture task from first substantive prompt
if (-not (Test-Path $taskFile) -and $prompt -and $prompt.Length -gt 10) {
    try { $prompt.Trim() | Set-Content $taskFile -Encoding UTF8 } catch {}
}

if (-not (Test-Path $taskFile)) {
    @{ count = $count; last_echo = $lastEcho } | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8
    exit 0
}

$taskContext = Get-Content $taskFile -Raw -Encoding UTF8
if (-not $taskContext.Trim()) { exit 0 }

# Check if time to echo
if (($count - $lastEcho) -lt $echoInterval) {
    @{ count = $count; last_echo = $lastEcho } | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8
    exit 0
}

$reminder = "[echo-of-prompt #$count]`n$taskContext`n[Re-read. Verify current action still serves the original task.]"
@{ count = $count; last_echo = $count } | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8
Write-Output (@{ hookSpecificOutput = @{ hookEventName = "UserPromptSubmit"; additionalContext = $reminder } } | ConvertTo-Json -Compress)
exit 0
