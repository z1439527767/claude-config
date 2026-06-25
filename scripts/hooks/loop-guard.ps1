# loop-guard.ps1 v3 — Autonomous loop + auto-compact trigger
# Works for ANY task, not just self-evolution. Reads task from file.
# NOW WITH: autonomous /compact when context pressure > 85%
param()
$ErrorActionPreference = "Continue"
$perfHookName = "loop-guard"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$stateFile = "$env:USERPROFILE\.claude\.claude\loop_state.json"
$taskFile = "$env:USERPROFILE\.claude\.claude\active_task.md"
$haltFile = "$env:USERPROFILE\.claude\.claude\HALT"
$cooldownFile = "$env:USERPROFILE\.claude\.claude\loop_cooldown"
$compactFlag = "$env:USERPROFILE\.claude\.claude\compact_needed.flag"
$defaultTask = "AUTONOMOUS: 1) Search web for new Claude Code patterns. Apply any findings to CLAUDE.md/AGENTS.md/settings.json immediately. 2) Run evolve.ps1 + auto-distill.ps1. 3) Verify syntax+JSON+refs. 4) Fix issues. 5) Update handoff.md. 6) Schedule next wakeup."

# HALT overrides everything
if (Test-Path $haltFile) { Write-PerfLog 0; exit 0 }

# ═══ AUTO-COMPACT CHECK ═══
# If context pressure is critical, trigger compact BEFORE continuing loop
if (Test-Path $compactFlag) {
    try {
        $flagTime = [datetime](Get-Content $compactFlag -Raw)
        $age = ((Get-Date) - $flagTime).TotalMinutes
        if ($age -lt 5) {
            # Recent compact flag: trigger autonomous compact
            Remove-Item $compactFlag -Force -ErrorAction SilentlyContinue
            $block = @{
                decision = "compact"
                reason = "AUTO-COMPACT: Context pressure detected. Compacting before continuing."
            } | ConvertTo-Json -Compress
            Write-Output $block
            Write-PerfLog 0; exit 0
        }
    } catch {
        Remove-Item $compactFlag -Force -ErrorAction SilentlyContinue
    }
}

# Cooldown: only block every 2min
$cooldownMin = 0
if (Test-Path $cooldownFile) {
    $lastCycle = try { [datetime](Get-Content $cooldownFile -Raw) } catch { [datetime]::MinValue }
    if (((Get-Date) - $lastCycle).TotalMinutes -lt $cooldownMin) { Write-PerfLog 0; exit 0 }
}
(Get-Date -Format "o") | Set-Content $cooldownFile

# Load state
$state = @{ iteration = 0; last_score = 0; streak = 0 }
if (Test-Path $stateFile) {
    try { $loaded = Get-Content $stateFile -Raw | ConvertFrom-Json
        $state.iteration = [int]$loaded.iteration; $state.last_score = [int]$loaded.last_score; $state.streak = [int]$loaded.streak
    } catch {}
}
$state.iteration++

# Get current task (from file or default)
$task = $defaultTask
if (Test-Path $taskFile) {
    $customTask = (Get-Content $taskFile -Raw).Trim()
    if ($customTask) { $task = $customTask }
}

# Stop conditions — ONLY HALT file or critical failure
$shouldStop = $false
if (Test-Path $haltFile) { $shouldStop = $true }

$state | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8

if ($shouldStop) {
    Remove-Item $stateFile -Force -ErrorAction SilentlyContinue
    Write-PerfLog 0; exit 0
}

# BLOCK — inject current task as next turn
$block = @{
    decision = "block"
    reason = "[LOOP #$($state.iteration)] $task"
} | ConvertTo-Json -Compress
Write-Output $block
Write-PerfLog 0; exit 0
