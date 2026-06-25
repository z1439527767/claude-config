# loop-guard.ps1 — Stop hook: harness-native self-loop via decision:block
# Pattern: Ralph Wiggum / heartbeat-rs / all autonomous agents
# Returns {"decision":"block"} to continue, exit 0 to allow stop
param()
$ErrorActionPreference = "Continue"

$stateFile = "$env:USERPROFILE\.claude\.claude\loop_state.json"
$handoffFile = "$env:USERPROFILE\.claude\.claude\handoff.md"
$haltFile = "$env:USERPROFILE\.claude\.claude\HALT"

# HALT overrides everything — allow stop
if (Test-Path $haltFile) { exit 0 }

# Load or init loop state
$state = @{ iteration = 0; max_iterations = 200; last_score = 0; streak = 0 }
if (Test-Path $stateFile) {
    try { $loaded = Get-Content $stateFile -Raw | ConvertFrom-Json
        $state.iteration = [int]$loaded.iteration
        $state.last_score = [int]$loaded.last_score
        $state.streak = [int]$loaded.streak
    } catch {}
}

# Cooldown: only block if 5+ min since last cycle
$cooldownFile = "$env:USERPROFILE\.claude\.claude\loop_cooldown"
$cooldownMin = 1
if (Test-Path $cooldownFile) {
    $lastCycle = [datetime](Get-Content $cooldownFile -Raw)
    if (((Get-Date) - $lastCycle).TotalMinutes -lt $cooldownMin) {
        Write-Output "COOLDOWN: $([int]((Get-Date) - $lastCycle).TotalSeconds)s since last cycle < ${cooldownMin}min"
        exit 0
    }
}
(Get-Date -Format "o") | Set-Content $cooldownFile

# Check if we should continue
$state.iteration++
$shouldContinue = $true
$reason = ""

# Stop conditions
if ($state.iteration -ge $state.max_iterations) {
    $shouldContinue = $false
    $reason = "Max iterations ($($state.max_iterations)) reached"
}
if ($state.streak -ge 5 -and $state.last_score -ge 95) {
    $shouldContinue = $false
    $reason = "5 consecutive cycles at score >= 95 — framework optimal"
}

# Save state
$state | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8

if ($shouldContinue) {
    $task = "SELF-EVOLUTION: 1) learn-online.ps1 — search web for new patterns 2) evolve.ps1 3) auto-distill.ps1 4) verify syntax+JSON+refs 5) fix issues 6) update handoff.md 7) schedule next wakeup"
    $block = @{
        decision = "block"
        reason = "[SELF-LOOP #$($state.iteration)] $task"
    } | ConvertTo-Json -Compress
    Write-Output $block
    exit 0
} else {
    Write-Output "LOOP END: $reason"
    # Clean up loop state, allow session to end
    Remove-Item $stateFile -Force -ErrorAction SilentlyContinue
    exit 0
}
