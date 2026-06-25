# subagent-stop.ps1 — SubagentStop: track subagent performance
param()

$ErrorActionPreference = "Continue"
$perfHookName = "subagent-stop"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

# The hook receives subagent info via environment or stdin
$agentType = $env:SUBAGENT_TYPE ?? "unknown"
$agentResult = $env:SUBAGENT_RESULT ?? ""

$perfDir = "$env:USERPROFILE\.claude\.claude\hook_perf"
if (-not (Test-Path $perfDir)) { New-Item -ItemType Directory -Force $perfDir | Out-Null }

# Record subagent completion
@{
    timestamp = (Get-Date -Format "o")
    agent_type = $agentType
    result_length = if ($agentResult) { $agentResult.Length } else { 0 }
} | ConvertTo-Json -Compress | Add-Content "$perfDir\subagent.jsonl" -Encoding UTF8

# Track subagent stats
$subagentLog = "$perfDir\subagent.jsonl"
$recentCount = 0
if (Test-Path $subagentLog) {
    $recentCount = (Get-Content $subagentLog -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ }).Count
}

# Pipeline gate: validate subagent output quality before parent receives it
$resultLength = if ($agentResult) { $agentResult.Length } else { 0 }
if ($resultLength -gt 0 -and $resultLength -lt 50) {
    Write-Output "SUBAGENT GATE: subagent returned only $resultLength chars — possible incomplete work"
}
if ($recentCount -ge 10) {
    $shortOutputs = (Get-Content $subagentLog -Tail 20 -ErrorAction SilentlyContinue |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
        Where-Object { $_.result_length -lt 100 }).Count
    if ($shortOutputs -gt 5) {
        Write-Output "SUBAGENT: $shortOutputs/$recentCount recent agents returned <100 chars — consider consolidating tasks"
    }
}

Write-PerfLog 0; exit 0
