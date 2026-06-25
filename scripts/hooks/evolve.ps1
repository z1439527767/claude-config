# evolve.ps1 — SessionStart: self-evolution orchestrator (split from 497→50 lines)
# Sources lib/evolve-*.ps1 for L1-L5 logic
param()
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$perfHookName = "evolve"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$script:applied = @()
$script:changes = @()
$libDir = "$env:USERPROFILE\.claude\scripts\lib"

# ── Gate check ──
. "$libDir\evolve-gate.ps1"
if (-not $script:canEvolve) {
    Write-Output "EVOLVE: gated — $script:gateReason"
    Write-PerfLog 0; exit 0
}

# ── L1-L5 in order ──
. "$libDir\evolve-L1.ps1"
. "$libDir\evolve-L2.ps1"
. "$libDir\evolve-L3.ps1"
. "$libDir\evolve-L5.ps1"

# ── Verify & rollback ──
. "$libDir\evolve-verify.ps1"

# ── Log, gate update, report ──
$allChanges = @($script:applied) + @($script:changes)
$evolveLog = "$env:USERPROFILE\.claude\.claude\evolution_log.jsonl"

if ($allChanges.Count -gt 0) {
    $event = @{ timestamp = (Get-Date -Format "o"); type = "evolution"; changes = $allChanges }
    $eventJson = $event | ConvertTo-Json -Compress
    $eventJson | Add-Content $evolveLog -Encoding UTF8
    try { python3 "$env:USERPROFILE\.claude\scripts\adapter-db.py" insert evolution_log "" $eventJson 2>$null | Out-Null } catch {}

    $logLines = @(Get-Content $evolveLog -Encoding UTF8 | Where-Object { $_ })
    if ($logLines.Count -gt 100) { $logLines[-80..-1] | Set-Content $evolveLog -Encoding UTF8 }
}

if ($script:applied.Count -gt 0) {
    $gateFile = "$env:USERPROFILE\.claude\.claude\evo_gate.json"
    $gateData = @{
        last_evolution = (Get-Date -Format "o"); session_count_since_last = 0
        recent_evo_timestamps = @(); rule_additions_this_cycle = 0
    }
    if (Test-Path $gateFile) {
        try {
            $existing = Get-Content $gateFile -Raw | ConvertFrom-Json
            $recentTs = @($existing.recent_evo_timestamps) + @((Get-Date -Format "o"))
            $gateData.recent_evo_timestamps = @($recentTs | Select-Object -Last 15)
            $l1Adds = ($script:applied | Where-Object { $_ -match "^L1:" }).Count
            $gateData.rule_additions_this_cycle = [int]$existing.rule_additions_this_cycle + $l1Adds
        } catch {}
    }
    $gateData | ConvertTo-Json | Set-Content $gateFile -Encoding UTF8

    $snapshotScript = "$env:USERPROFILE\.claude\scripts\hooks\git-snapshot.ps1"
    if (Test-Path $snapshotScript) {
        $changeSummary = ($allChanges -join "; ")
        if ($changeSummary.Length -gt 200) { $changeSummary = $changeSummary.Substring(0, 200) + "…" }
        & pwsh -ExecutionPolicy Bypass -File $snapshotScript -Message "evo: $changeSummary" 2>$null
    }

    $msg = ($allChanges | ForEach-Object { "  $_" }) -join "`n"
    Write-Output "EVOLVE:`n$msg"
}

# Cleanup: truncate large perf files
$perfDir = "$env:USERPROFILE\.claude\.claude\hook_perf"
if (Test-Path $perfDir) {
    Get-ChildItem $perfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -gt 500000 } |
        ForEach-Object { $keep = Get-Content $_.FullName -Tail 100 -Encoding UTF8; $keep | Set-Content $_.FullName -Encoding UTF8 }
}

Write-PerfLog 0; exit 0
