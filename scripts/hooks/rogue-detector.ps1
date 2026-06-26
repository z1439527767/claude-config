# rogue-detector.ps1 — PostToolUse: detect anomalous tool usage patterns
# Distilled from Microsoft Agent SRE spec: z-score 2.5/60s window, entropy 0.3/3.5
param()
$ErrorActionPreference = "Continue"

# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "rogue-detector" -EntityName "hook-rogue-detector-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("rogue-detector executed at $(Get-Date -Format 'o')") -Priority "low"
$stateFile = "$env:USERPROFILE\.claude\session-env\rogue_state.json"
$allowedTools = @('Read','Write','Edit','Bash','PowerShell','Glob','Grep','WebFetch','WebSearch',
    'TaskCreate','TaskUpdate','Agent','Skill','Workflow','AskUserQuestion','mcp__memory__*','mcp__comfyui__*')

$now = Get-Date

# Load or init state
$state = @{ calls = @(); baseline_mean = $null; baseline_std = $null; alert_count = 0 }
if (Test-Path $stateFile) {
    try { $state = Get-Content $stateFile -Raw | ConvertFrom-Json } catch {}
}

# Record tool call (from env vars set by hook)
$toolName = $env:CLAUDE_TOOL_NAME
if (-not $toolName) { exit 0 }

$state.calls += @{ tool = $toolName; t = $now.ToString("o") }

# Keep sliding window: 5 minutes
$windowStart = $now.AddMinutes(-5).ToString("o")
$windowCalls = @($state.calls | Where-Object { $_.t -ge $windowStart })
$state.calls = @($state.calls | Select-Object -Last 200)

# ── Signal 1: Frequency anomaly (z-score > 2.5) ──
$callCount = $windowCalls.Count
if ($callCount -ge 20 -and $state.baseline_mean) {
    $zScore = if ($state.baseline_std -gt 0) { ($callCount - $state.baseline_mean) / $state.baseline_std } else { 0 }
    if ([Math]::Abs($zScore) -gt 2.5) {
        Write-Output "ROGUE: abnormal call frequency z=$([Math]::Round($zScore,1)) in 5min ($callCount calls)"
    }
}

# Update baseline (once we have enough data)
if ($callCount -ge 10) {
    $recentCounts = @()
    for ($i = 0; $i -lt [Math]::Min(10, $state.calls.Count / 10); $i++) {
        $start = $i * 10; $end = [Math]::Min($start + 10, $state.calls.Count)
        $recentCounts += ($state.calls[$start..($end-1)] | Measure-Object).Count
    }
    if ($recentCounts.Count -ge 3) {
        $state.baseline_mean = ($recentCounts | Measure-Object -Average).Average
        $state.baseline_std = [Math]::Sqrt(($recentCounts | ForEach-Object { ($_ - $state.baseline_mean) * ($_ - $state.baseline_mean) } | Measure-Object -Sum).Sum / $recentCounts.Count)
    }
}

# ── Signal 2: Tool diversity entropy check ──
$toolCounts = @{}
foreach ($c in $windowCalls) {
    if (-not $toolCounts[$c.tool]) { $toolCounts[$c.tool] = 0 }
    $toolCounts[$c.tool]++
}
$totalCalls = $windowCalls.Count
$entropy = 0.0
foreach ($count in $toolCounts.Values) {
    $p = $count / $totalCalls
    if ($p -gt 0) { $entropy -= $p * [Math]::Log($p) }
}
$maxEntropy = [Math]::Log([Math]::Max($toolCounts.Count, 1))
$normalizedEntropy = if ($maxEntropy -gt 0) { $entropy / $maxEntropy } else { 0 }

if ($totalCalls -ge 10 -and $normalizedEntropy -lt 0.3) {
    Write-Output "ROGUE: low tool diversity (entropy=$([Math]::Round($normalizedEntropy,2))), possible tunnel vision"
}

# Save state
$state | ConvertTo-Json -Depth 3 | Set-Content $stateFile -Encoding UTF8
exit 0
