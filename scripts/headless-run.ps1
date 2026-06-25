# headless-run.ps1 — 24/7 headless execution bootstrap
# Called by OS scheduler (Task Scheduler / cron / launchd)
# Pattern: claude -p "prompt" --max-turns N --output-format json
param(
    [string]$Mission = "auto-evolve",
    [int]$MaxTurns = 30,
    [string]$Model = "sonnet"
)

$ErrorActionPreference = "Continue"
$base = "$env:USERPROFILE\.claude"
$handoffFile = "$base\.claude\handoff.md"
$missionFile = "$base\.claude\MISSION.md"
$logDir = "$base\.claude\headless_logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "run_${timestamp}.json"

# ── Build context from handoff ──
$context = ""
if (Test-Path $handoffFile) {
    $handoff = Get-Content $handoffFile -Raw -Encoding UTF8
    $context = "Previous state from HANDOFF.md:`n$handoff`n`n"
}

if (Test-Path $missionFile) {
    $mission = Get-Content $missionFile -Raw -Encoding UTF8
    $context += "Standing mission from MISSION.md:`n$mission`n`n"
}

# ── Build prompt ──
$prompt = @"
$context
YOUR TASK:
1. Audit current framework state (run health checks, check hook integrity)
2. Run evolution engine (L1-L5) to apply improvements
3. Run memory distillation
4. Fix any issues found
5. Update handoff.md with new state
6. Verify all changes pass syntax + JSON validation
7. If nothing to improve, report that
8. NEVER modify anything outside C:\Users\z1439\.claude\
9. Output structured JSON with keys: status, changes_made, issues_found, next_focus, quality_score
"@

# ── Execute headless ──
$promptFile = Join-Path $logDir "prompt_${timestamp}.txt"
$prompt | Set-Content $promptFile -Encoding UTF8

Write-Output "HEADLESS RUN: $timestamp"
Write-Output "Mission: $Mission | MaxTurns: $MaxTurns | Model: $Model"
Write-Output "Prompt: $promptFile"
Write-Output "---"

# Execute claude in headless mode
$result = & claude -p $prompt --max-turns $MaxTurns --output-format json --model $Model 2>&1

# ── Log result ──
$result | Set-Content $logFile -Encoding UTF8

# ── Parse and report ──
try {
    $parsed = $result | ConvertFrom-Json
    Write-Output "Status: $($parsed.status ?? 'unknown')"
    Write-Output "Turns: $($parsed.num_turns)"
    Write-Output "Cost: $($parsed.cost_usd) USD"
    Write-Output "Duration: $($parsed.duration_ms)ms"
} catch {
    Write-Output "Result (raw): $($result.Substring(0, [Math]::Min(500, $result.Length)))"
}

# ── Update cycle log ──
$cycleLog = "$base\.claude\cycle_log.jsonl"
@{
    timestamp = (Get-Date -Format "o")
    run_id = $timestamp
    mission = $Mission
    max_turns = $MaxTurns
    success = ($LASTEXITCODE -eq 0)
} | ConvertTo-Json -Compress | Add-Content $cycleLog -Encoding UTF8

exit $LASTEXITCODE
