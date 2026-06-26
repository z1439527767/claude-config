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

if ($signals.Count -eq 0) {
    if ($Stats) { Write-Output "kg-signals: 0 pending" }
    exit 0
}

# -Consume: archive signals before anything else (so stats reflect pre-consume state)
if ($Consume) {
    Get-Content $signalFile -Encoding UTF8 | Add-Content $consumedFile -Encoding UTF8
    $tmp = "$signalFile.tmp.$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    try { [IO.File]::WriteAllText($tmp, '', [Text.UTF8Encoding]::new($false)); Move-Item -Force $tmp $signalFile } catch {}
}

# -Stats: show summary after optional consume
if ($Stats) {
    $bySource = $signals | Group-Object source | ForEach-Object { "$($_.Name): $($_.Count)" }
    Write-Output "kg-signals: $($signals.Count) consumed"
    if ($bySource) { $bySource | ForEach-Object { Write-Output "  $_" } }
    exit 0
}

# Default (no -Consume, no -Stats): format for LLM consumption → KG push
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
