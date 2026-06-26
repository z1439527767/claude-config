# sync-kg.ps1 — Hook→KG signal bridge
# Hooks can't call MCP tools directly. They write signals → LLM reads → pushes to KG.
# This script: reads signals, deduplicates, formats for LLM consumption.
param([switch]$Consume, [switch]$Stats)

$ErrorActionPreference = "Continue"
$signalFile = "$env:USERPROFILE\.claude\.claude\kg_signals.jsonl"
$consumedFile = "$env:USERPROFILE\.claude\.claude\kg_signals_consumed.jsonl"

if (-not (Test-Path $signalFile)) {
    if ($Stats) { Write-Output "kg-signals: 0 pending" }
    exit 0
}

$signals = @(Get-Content $signalFile -Encoding UTF8 -ErrorAction SilentlyContinue |
    Where-Object { $_.Trim() -ne '' } |
    ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
    Where-Object { $_ })

if ($Stats) {
    $bySource = $signals | Group-Object source | ForEach-Object { "$($_.Name): $($_.Count)" }
    Write-Output "kg-signals: $($signals.Count) pending"
    if ($bySource) { $bySource | ForEach-Object { Write-Output "  $_" } }
    exit 0
}

if ($signals.Count -eq 0) { exit 0 }

# Format for LLM: each signal is a ready-to-use KG operation
$output = @()
foreach ($s in $signals) {
    $output += @{
        source    = $s.source
        timestamp = $s.timestamp
        entity    = $s.entity
        entityType = $s.entityType
        observations = $s.observations
        relations = $s.relations
        priority  = if ($s.priority) { $s.priority } else { "normal" }
    }
}

$output | ConvertTo-Json -Depth 4

if ($Consume) {
    # Move processed signals to consumed log
    Get-Content $signalFile -Encoding UTF8 | Add-Content $consumedFile -Encoding UTF8
    # Atomic truncate
    $tmp = "$signalFile.tmp.$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    try { "" | Set-Content $tmp -Encoding UTF8; Move-Item -Force $tmp $signalFile } catch {}
}
