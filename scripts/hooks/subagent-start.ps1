# subagent-start.ps1 — SubagentStart: log spawn events
param()
$ErrorActionPreference = "Continue"
$perfHookName = "subagent-start"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$logDir = "$env:USERPROFILE\.claude\.claude\subagent_logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }

$agentType = $env:CLAUDE_SUBAGENT_TYPE
$agentId = $env:CLAUDE_SUBAGENT_ID
if (-not $agentType) { $agentType = "unknown" }
if (-not $agentId) { $agentId = "unknown" }

$entry = @{
    timestamp   = (Get-Date -Format "o")
    agent_type  = $agentType
    agent_id    = $agentId.Substring(0, [Math]::Min(16, $agentId.Length))
} | ConvertTo-Json -Compress

Add-Content "$logDir\subagent_spawns.jsonl" -Value $entry -Encoding UTF8

# Keep only last 50
$lines = Get-Content "$logDir\subagent_spawns.jsonl" -Encoding UTF8 -ErrorAction SilentlyContinue
if ($lines.Count -gt 50) { $lines[-50..-1] | Set-Content "$logDir\subagent_spawns.jsonl" -Encoding UTF8 }

Write-PerfLog 0; exit 0
