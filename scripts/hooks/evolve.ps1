# evolve.ps1 — SessionStart: self-evolution orchestrator (split from 497→50 lines)
# Sources lib/evolve-*.ps1 for L1-L5 logic
param()
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$perfHookName = "evolve"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

# Concurrent-safety: flock via temp file. No two evolves run simultaneously.
$lockFile = "$env:USERPROFILE\.claude\.claude\evo.lock"
if (Test-Path $lockFile) {
    $lockAge = (Get-Date) - (Get-Item $lockFile).LastWriteTime
    if ($lockAge.TotalMinutes -lt 10) {
        Write-Output "EVOLVE: locked (another evolve running, $([math]::Round($lockAge.TotalSeconds))s ago)"
        Write-PerfLog 0; exit 0
    }
    # Stale lock (>10 min) — previous evolve crashed, clean up and proceed
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
}
try { New-Item -ItemType File $lockFile -Force | Out-Null } catch {
    Write-Output "EVOLVE: cannot create lock file: $_"
    Write-PerfLog 1; exit 1
}

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
    try { python "$env:USERPROFILE\.claude\scripts\adapter-db.py" insert evolution_log "" $eventJson 2>$null | Out-Null } catch {
        $eventJson | Add-Content $evolveLog -Encoding UTF8
    }

    $logLines = @(Get-Content $evolveLog -Encoding UTF8 | Where-Object { $_ })
    if ($logLines.Count -gt 100) {
        $keep = $logLines[-80..-1]
        $tmpLog = "$evolveLog.tmp.$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        try { $keep | Set-Content $tmpLog -Encoding UTF8; Move-Item -Force $tmpLog $evolveLog } catch { if (Test-Path $tmpLog) { Remove-Item $tmpLog -Force -ErrorAction SilentlyContinue } }
    }
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

# Release concurrent-safety lock (set at script start)
if (Test-Path $lockFile) { Remove-Item $lockFile -Force -ErrorAction SilentlyContinue }

Write-PerfLog 0; exit 0
