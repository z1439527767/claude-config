# loop-guard.ps1 v2 — Universal autonomous loop
# Works for ANY task, not just self-evolution. Reads task from file.
param()
$ErrorActionPreference = "Continue"

$stateFile = "$env:USERPROFILE\.claude\.claude\loop_state.json"
$taskFile = "$env:USERPROFILE\.claude\.claude\active_task.md"
$haltFile = "$env:USERPROFILE\.claude\.claude\HALT"
$cooldownFile = "$env:USERPROFILE\.claude\.claude\loop_cooldown"
$defaultTask = "AUTONOMOUS: 1) Search web for new Claude Code patterns. Apply any findings to CLAUDE.md/AGENTS.md/settings.json immediately. 2) Run evolve.ps1 + auto-distill.ps1. 3) Verify syntax+JSON+refs. 4) Fix issues. 5) Update handoff.md. 6) Schedule next wakeup."

# HALT overrides everything
if (Test-Path $haltFile) { exit 0 }

# Cooldown: only block every 2min
$cooldownMin = 2
if (Test-Path $cooldownFile) {
    $lastCycle = try { [datetime](Get-Content $cooldownFile -Raw) } catch { [datetime]::MinValue }
    if (((Get-Date) - $lastCycle).TotalMinutes -lt $cooldownMin) { exit 0 }
}
(Get-Date -Format "o") | Set-Content $cooldownFile

# Load state
$state = @{ iteration = 0; max_iterations = 500; last_score = 0; streak = 0 }
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

# Stop conditions
$shouldStop = $false
if ($state.iteration -ge $state.max_iterations) { $shouldStop = $true }
if ($state.streak -ge 5 -and $state.last_score -ge 95) { $shouldStop = $true }

$state | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8

if ($shouldStop) {
    Remove-Item $stateFile -Force -ErrorAction SilentlyContinue
    exit 0
}

# BLOCK — inject current task as next turn
$block = @{
    decision = "block"
    reason = "[LOOP #$($state.iteration)] $task"
} | ConvertTo-Json -Compress
Write-Output $block
exit 0
