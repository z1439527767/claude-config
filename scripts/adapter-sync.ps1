# adapter-sync.ps1 — Bidirectional file memory ↔ Knowledge Graph sync
# Usage:
#   adapter-sync.ps1 -ToKG          → sync local memory files → KG (create/update entities)
#   adapter-sync.ps1 -FromKG        → sync KG → local memory files (import new entities)
#   adapter-sync.ps1 -Diff          → show differences without syncing
#   adapter-sync.ps1 -Full          → bidirectional sync
param([switch]$ToKG, [switch]$FromKG, [switch]$Diff, [switch]$Full)

$ErrorActionPreference = "Continue"
$baseDir = "$env:USERPROFILE\.claude"
$memDir = "$baseDir\projects\C--Users-z1439--claude\memory"
$syncStateFile = "$baseDir\.claude\sync_state.json"

function Get-LocalManifest {
    $manifest = @{}
    Get-ChildItem $memDir -Recurse -Filter "*.md" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "MEMORY.md" } | ForEach-Object {
        $content = Get-Content $_.FullName -Raw -Encoding UTF8
        $lines = $content -split "`n"
        $meta = @{}
        $inFM = $false; $fmEnd = 0
        for ($i = 0; $i -lt [math]::Min($lines.Count, 30); $i++) {
            $line = $lines[$i].Trim()
            if ($i -eq 0 -and $line -eq "---") { $inFM = $true; continue }
            if ($inFM -and $line -eq "---") { $fmEnd = $i; break }
            if ($inFM -and $line -match '^(\w+):\s*(.*)') {
                $meta[$Matches[1]] = $Matches[2]
            }
        }
        $body = ($lines[($fmEnd + 1)..($lines.Count - 1)] | Where-Object { $_ }) -join "`n"
        $atomicId = $meta["atomic_id"]
        if ($atomicId) {
            $manifest[$atomicId] = @{
                rel_path = $_.FullName.Replace($memDir, "").TrimStart("\")
                name = $meta["name"]
                type = $meta["type"]
                domain = $meta["domain"]
                confidence = $meta["confidence"]
                superseded_by = $meta["superseded_by"]
                body_preview = ($body -replace '\s+', ' ').Substring(0, [math]::Min(200, $body.Length))
            }
        }
    }
    return $manifest
}

function Get-SyncState {
    if (Test-Path $syncStateFile) {
        try { return Get-Content $syncStateFile -Raw | ConvertFrom-Json } catch { return @{} }
    }
    return @{ last_full_sync = $null; kg_entities = @(); local_ids = @() }
}

function Save-SyncState($state) {
    $state.updated = (Get-Date -Format "o")
    $state | ConvertTo-Json -Depth 5 | Set-Content $syncStateFile -Encoding UTF8
}

# ── Diff Mode ──
if ($Diff) {
    $local = Get-LocalManifest
    $state = Get-SyncState

    Write-Output "═══ Local Memory Files ═══"
    foreach ($id in $local.Keys | Sort-Object) {
        $entry = $local[$id]
        $ss = if ($entry.superseded_by) { " [→ $($entry.superseded_by)]" } else { "" }
        Write-Output "  [$id] $($entry.type)/$($entry.domain): $($entry.name)$ss"
    }

    Write-Output "`n═══ Sync State ═══"
    Write-Output "  Last full sync: $($state.last_full_sync)"
    Write-Output "  KG entities tracked: $($state.kg_entities.Count)"
    Write-Output "  Local IDs tracked: $($state.local_ids.Count)"

    $newIds = $local.Keys | Where-Object { $_ -notin $state.local_ids }
    $removedIds = $state.local_ids | Where-Object { $_ -notin $local.Keys }
    if ($newIds) { Write-Output "`n  NEW (local→KG): $($newIds -join ', ')" }
    if ($removedIds) { Write-Output "  REMOVED (stale KG): $($removedIds -join ', ')" }
    if (-not $newIds -and -not $removedIds) { Write-Output "`n  ✅ In sync" }

    Write-Output "`n═══ Sync Commands ═══"
    Write-Output "  To push local → KG: adapter-sync.ps1 -ToKG"
    Write-Output "  To pull KG → local: adapter-sync.ps1 -FromKG"
    Write-Output "  To run full sync:   adapter-sync.ps1 -Full"
    exit 0
}

# ── ToKG Mode ──
if ($ToKG -or $Full) {
    $local = Get-LocalManifest
    $state = Get-SyncState
    $synced = 0

    Write-Output "═══ Syncing local → KG ═══"

    foreach ($id in $local.Keys | Sort-Object) {
        $entry = $local[$id]
        if ($id -in $state.local_ids) { continue }  # Already synced

        # Build KG entity
        $entityName = "[$id] $($entry.name)"
        $entityType = ($entry.type -eq "feedback") ? "Insight" : "Preference"
        $observations = @(
            "Type: $($entry.type)",
            "Domain: $($entry.domain)",
            "Confidence: $($entry.confidence)",
            "Summary: $($entry.body_preview)"
        )
        if ($entry.superseded_by) {
            $observations += "Superseded by: $($entry.superseded_by)"
        }

        Write-Output "  → KG: $entityName"
        Write-Output "    Observations: $($observations.Count) fields"
        Write-Output "    (Use mcp__memory__create_entities to actually create)"

        $state.local_ids += @($id)
        $synced++
    }

    # Clean up stale
    $stale = $state.local_ids | Where-Object { $_ -notin $local.Keys }
    if ($stale) {
        Write-Output "  Stale (would remove from KG): $($stale -join ', ')"
    }

    $state.last_full_sync = (Get-Date -Format "o")
    Save-SyncState $state
    Write-Output "Synced: $synced new, $($local.Count) total local entries"
}

# ── FromKG Mode ──
if ($FromKG -or $Full) {
    Write-Output "═══ Syncing KG → local ═══"
    Write-Output "  NOTE: Run 'mcp__memory__read_graph' first to get KG state."
    Write-Output "  Then compare with local manifest via -Diff to find KG-only entities."
    Write-Output "  KG entities without local files can be created with memory-create.py."
}

Write-Output "✅ Sync complete"
