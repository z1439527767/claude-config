# daemon.ps1 — 24/7 autonomous execution harness
# Episode-based loop with structured handoffs + crash recovery
param(
    [int]$MaxCycles = 100,
    [int]$CycleMinutes = 10,
    [int]$TokenBudgetPerCycle = 100000
)

$ErrorActionPreference = "Continue"
$base = "$env:USERPROFILE\.claude"
$missionFile = "$base\.claude\MISSION.md"
$handoffFile = "$base\.claude\handoff.md"
$cycleLog = "$base\.claude\cycle_log.jsonl"
$haltFile = "$base\.claude\HALT"

$cycle = 0
$consecutiveNoImprovement = 0
$totalTokens = 0

Write-Output "DAEMON START: max $MaxCycles cycles, ${CycleMinutes}min each, ${TokenBudgetPerCycle} token budget"
Write-Output "Mission: $(if(Test-Path $missionFile){'LOADED'}else{'MISSING'})"
Write-Output "Handoff: $(if(Test-Path $handoffFile){'LOADED'}else{'MISSING'})"

while ($cycle -lt $MaxCycles) {
    $cycle++
    $cycleStart = Get-Date
    Write-Output "`n=== CYCLE $cycle / $MaxCycles @ $(Get-Date -Format 'HH:mm:ss') ==="

    # ── Check halt signal ──
    if (Test-Path $haltFile) {
        $reason = Get-Content $haltFile -Raw
        Write-Output "HALT: $reason"
        break
    }

    # ── 1. RECONSTRUCT: read handoff ──
    $handoff = $null
    if (Test-Path $handoffFile) {
        try { $handoff = Get-Content $handoffFile -Raw -Encoding UTF8 } catch {}
    }
    Write-Output "  RECONSTRUCT: handoff $(if($handoff){'loaded'}else{'missing'})"

    # ── 2. AUDIT: run health + perf check ──
    Write-Output "  AUDIT: running health checks..."
    $healthResult = & pwsh -ExecutionPolicy Bypass -File "$base\scripts\hooks\session-start.ps1" 2>&1
    $healthOk = ($LASTEXITCODE -eq 0)
    Write-Output "  AUDIT: health $($healthOk ? 'PASS' : 'ISSUES')"

    # ── 3. IMPROVE: run evolve ──
    Write-Output "  IMPROVE: running evolution engine..."
    $evoResult = & pwsh -ExecutionPolicy Bypass -File "$base\scripts\hooks\evolve.ps1" 2>&1
    $evoOk = ($LASTEXITCODE -eq 0)
    if ($evoResult -match 'EVOLVE:') {
        Write-Output "  IMPROVE: changes applied"
    } else {
        Write-Output "  IMPROVE: no changes needed"
        $consecutiveNoImprovement++
    }

    # ── 4. VERIFY: final syntax + JSON check ──
    Write-Output "  VERIFY: running final validation..."
    $verifyOk = $true
    try { Get-Content "$base\settings.json" -Raw | ConvertFrom-Json | Out-Null } catch { $verifyOk = $false }
    Get-ChildItem "$base\scripts\hooks\*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
        $nullVar = $null; $pe = @()
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$nullVar, [ref]$pe)
        if ($pe.Count -gt 0) { $verifyOk = $false }
    }
    Write-Output "  VERIFY: $($verifyOk ? 'PASS' : 'FAIL')"

    # ── 5. HANDOFF: write state for next cycle ──
    $duration = [int]((Get-Date) - $cycleStart).TotalSeconds
    $handoffContent = @"
# HANDOFF — Episode State
<!-- Last updated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') -->

## Episode: $cycle
## Status: COMPLETE

## Current State
- Cycle duration: ${duration}s
- Health check: $($healthOk ? 'PASS' : 'ISSUES')
- Evolution: $($evoOk ? 'applied' : 'no changes')
- Verification: $($verifyOk ? 'PASS' : 'FAIL')
- Consecutive no-improvement: $consecutiveNoImprovement

## Completed This Cycle
$($evoResult -replace '\n', "`n  ")

## Next Episode Focus
$(if ($consecutiveNoImprovement -ge 3) { '- ESCALATE: 3 cycles no improvement — suggest user review' } elseif (-not $verifyOk) { '- EMERGENCY: verification failed — run manual health check' } else { '- Continue optimization cycle' })
"@
    Set-Content $handoffFile -Value $handoffContent -Encoding UTF8

    # ── Log cycle ──
    @{
        timestamp = (Get-Date -Format "o")
        cycle = $cycle
        duration_s = $duration
        health_ok = $healthOk
        evo_applied = $evoOk
        verify_ok = $verifyOk
    } | ConvertTo-Json -Compress | Add-Content $cycleLog -Encoding UTF8

    # ── Check termination ──
    if (-not $verifyOk) {
        Write-Output "TERMINATE: verification failed"
        break
    }
    if ($consecutiveNoImprovement -ge 5) {
        Write-Output "TERMINATE: 5 cycles no improvement"
        break
    }

    # ── Sleep until next cycle ──
    $sleepTime = [math]::Max(60, ($CycleMinutes * 60) - $duration)
    Write-Output "SLEEP: ${sleepTime}s until next cycle..."
    Start-Sleep -Seconds $sleepTime
}

Write-Output "`nDAEMON END: $cycle cycles completed"
