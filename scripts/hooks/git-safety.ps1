# Git Safety PreToolUse Hook (Bash matcher)
# Blocks --no-verify, --no-gpg-sign, -c commit.gpgsign=false, and force push to main/master
$sw = [Diagnostics.Stopwatch]::StartNew()
function _p($c) { $d="$env:USERPROFILE\.claude\.claude\hook_perf"; if(-not(Test-Path $d)){mkdir -Force $d|Out-Null}; @{t=(Get-Date -Format "o");h="git-safety";d=$sw.ElapsedMilliseconds;e=$c}|ConvertTo-Json -Compress|Add-Content "$d\git-safety.jsonl" -Encoding UTF8 }
$toolInput = $env:CLAUDE_TOOL_INPUT
$ErrorActionPreference = "SilentlyContinue"
if (-not $toolInput) {
    try {
        $stdin = [Console]::In.ReadToEnd()
        if ($stdin) {
            $json = $stdin | ConvertFrom-Json
            $toolInput = if ($json.tool_input.command) { $json.tool_input.command }
                        elseif ($json.tool_input -is [string]) { $json.tool_input }
                        else { $json.tool_input | ConvertTo-Json -Compress }
        }
    } catch { }
}

if ($toolInput) {
    if ($toolInput -match '--no-verify\b') {
        Write-Output '{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "GIT SAFETY: --no-verify blocked. Run hooks properly." } }'
        exit 2
    }
    if ($toolInput -match '--no-gpg-sign\b') {
        Write-Output '{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "GIT SAFETY: --no-gpg-sign blocked. Sign commits properly." } }'
        exit 2
    }
    if ($toolInput -match '-c\s+commit\.gpgsign\s*=\s*false') {
        Write-Output '{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "GIT SAFETY: -c commit.gpgsign=false blocked. Sign commits properly." } }'
        exit 2
    }
    if ($toolInput -match '--force\s+(origin/)?(main|master)') {
        Write-Output '{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "GIT SAFETY: force push to main/master blocked." } }'
        exit 2
    }
}
Write-Output '{}'
_p 0
