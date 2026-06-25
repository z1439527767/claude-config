# pre-write-snapshot.ps1 — PreToolUse: snapshot file before Write/Edit for rollback
# OpenHands-inspired event sourcing: every mutation has a reversible snapshot
param(
    [string]$tool_name = "",
    [string]$tool_input = ""
)

$ErrorActionPreference = "Continue"
$perfHookName = "pre-write-snapshot"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

# Only snapshot for Write and Edit operations
if ($tool_name -notin @("Write", "Edit")) { exit 0 }

# Parse tool input to extract file_path
try {
    $input = $tool_input | ConvertFrom-Json
    $filePath = $input.file_path
} catch { exit 0 }

if (-not $filePath -or -not (Test-Path $filePath)) {
    # New file — nothing to snapshot, but record the intent
    $newFileRecord = @{
        timestamp = (Get-Date -Format "o")
        operation = $tool_name
        file_path = $filePath
        action     = "create"
        size_before = 0
    }
    $newFileRecord | ConvertTo-Json -Compress | Add-Content "$env:USERPROFILE\.claude\.claude\snapshots\create_log.jsonl" -Encoding UTF8
    Write-PerfLog 0; exit 0
}

# ── Save snapshot ──
$snapshotDir = "$env:USERPROFILE\.claude\.claude\snapshots"
if (-not (Test-Path $snapshotDir)) {
    New-Item -ItemType Directory -Force $snapshotDir | Out-Null
}

try {
    $content = Get-Content $filePath -Raw -Encoding UTF8 -ErrorAction Stop
    $fileSize = (Get-Item $filePath).Length
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
    $safeName = $filePath -replace '[\\/:*?"<>|]', '_' -replace '^_+', ''
    $snapshotFile = "$snapshotDir\$($timestamp)_$safeName"

    # Store snapshot with metadata header
    $metadata = @{
        timestamp   = (Get-Date -Format "o")
        original    = $filePath
        operation   = $tool_name
        size        = $fileSize
        snapshot_id = $timestamp
    } | ConvertTo-Json -Compress

    # Format: JSON metadata line + content
    $metadata + "`n" + $content | Set-Content $snapshotFile -Encoding UTF8 -NoNewline

    # Rotate: keep max 50 snapshots (oldest first)
    $allSnapshots = Get-ChildItem $snapshotDir -File |
        Where-Object { $_.Name -match '^\d{17}_.+' } |
        Sort-Object LastWriteTime
    if ($allSnapshots.Count -gt 50) {
        $allSnapshots | Select-Object -First ($allSnapshots.Count - 50) | Remove-Item -Force
    }
} catch {
    # Never block on snapshot failure — but log it
    $errEntry = @{
        timestamp = (Get-Date -Format "o")
        error     = $_.Exception.Message
        file      = $filePath
    } | ConvertTo-Json -Compress
    $errEntry | Add-Content "$snapshotDir\errors.jsonl" -Encoding UTF8
}

Write-PerfLog 0; exit 0
