# evolve-trigger.ps1 — SessionEnd: trigger black hole engine SCAN + DIGEST
# Absorbs session data into brain. Does NOT retrain (that's the engine's decision).
param()
$ErrorActionPreference = "Continue"
$perfHookName = "evolve-trigger"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "evolve-trigger" -EntityName "hook-evolve-trigger-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("evolve-trigger executed at $(Get-Date -Format 'o')") -Priority "low"
# Only run if evolution engine exists
$engineScript = "$env:USERPROFILE\.claude\scripts\ralph-evolve-model.py"
if (-not (Test-Path $engineScript)) { exit 0 }

# Run SCAN + DIGEST only (no retraining — the engine decides threshold)
try {
    $result = python "$engineScript" --status 2>&1
    Write-Output "EVOLVE-TRIGGER: $result"
} catch {
    # Never block session end on evolution failure
}

Write-PerfLog 0; exit 0
