# session-end.ps1 v3 — Full Shutdown Sequence
# Diary → Dream → Intuition Update → Pack → Obsidian Sync → Cleanup → Quality
param()
$ErrorActionPreference = "Continue"
$perfHookName = "session-end"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$baseDir = "$env:USERPROFILE\.claude"

# ═══════════════════════════════════════════
# PHASE 1: Identity — Write Diary Entry
# ═══════════════════════════════════════════
try {
    $diaryContent = "Session completed. $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    python3 "$baseDir\scripts\identity-journal.py" --entry "$diaryContent" 2>$null | Out-Null
} catch {}

# ═══════════════════════════════════════════
# PHASE 2: Subconscious — Dream Mode
# ═══════════════════════════════════════════
try {
    python3 "$baseDir\scripts\subconscious.py" --mode dream 2>$null | Out-Null
} catch {}

# ═══════════════════════════════════════════
# PHASE 3: Intuition — Rebuild Index
# ═══════════════════════════════════════════
try {
    python3 "$baseDir\scripts\intuition-engine.py" --rebuild 2>$null | Out-Null
} catch {}

# ═══════════════════════════════════════════
# PHASE 4: Pack Session + Sync Obsidian
# ═══════════════════════════════════════════
try {
    $summary = python3 "$baseDir\scripts\session-summarizer.py" --json 2>$null
    if ($LASTEXITCODE -eq 0 -and $summary) {
        $summary | python3 "$baseDir\scripts\data-pack.py" --type session --source "session-summarizer" 2>$null | Out-Null
    }
} catch {}

try {
    python3 "$baseDir\scripts\packed-retrieve.py" --index 2>$null |
        Set-Content "$baseDir\packed\INDEX.md" -Encoding UTF8
} catch {}

try {
    python3 "$baseDir\scripts\obsidian-sync.py" push 2>$null | Out-Null
} catch {}

# ═══════════════════════════════════════════
# PHASE 5: Original Cleanup
# ═══════════════════════════════════════════
$summaryDir = "$baseDir\.claude\session_history"
if (-not (Test-Path $summaryDir)) { New-Item -ItemType Directory -Force $summaryDir | Out-Null }

# Hook activity count
$perfDir = "$baseDir\.claude\hook_perf"
$hookActivity = @{}
if (Test-Path $perfDir) {
    Get-ChildItem $perfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $count = (Get-Content $_.FullName -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ }).Count
        $hookActivity[$_.BaseName] = $count
    }
}

# Friction count
$frictionDir = "$baseDir\.claude\tellonce-state\friction"
$frictionCount = 0
if (Test-Path $frictionDir) {
    Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $frictionCount += (Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue | Where-Object { $_ }).Count
    }
}

# Evolved? Settings modified? CLAUDE.local.md updated?
$evolved = $false
$evolveLog = "$baseDir\.claude\evolution_log.jsonl"
if (Test-Path $evolveLog) {
    $lastLine = Get-Content $evolveLog -Tail 1 -ErrorAction SilentlyContinue
    if ($lastLine) {
        try { $lastEvo = $lastLine | ConvertFrom-Json; $evolved = ([datetime]$lastEvo.timestamp) -gt (Get-Date).AddHours(-2) } catch {}
    }
}

$localMdUpdated = (Get-Item "$baseDir\CLAUDE.local.md").LastWriteTime -gt (Get-Date).AddHours(-2)
$settingsModified = (Get-Item "$baseDir\settings.json").LastWriteTime -gt (Get-Date).AddHours(-2)

# Session summary
$summary = @{
    timestamp = (Get-Date -Format "o")
    hook_calls = $hookActivity
    friction_events = $frictionCount
    evolved = $evolved
    sedimentation = $localMdUpdated
    settings_modified = $settingsModified
}
$summaryFile = Join-Path $summaryDir "session_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
$summary | ConvertTo-Json -Depth 3 | Set-Content $summaryFile -Encoding UTF8

# Quality score
$qualityScore = 100
$qualityScore -= [math]::Min(50, $frictionCount * 10)
$failureDir = "$baseDir\.claude\tool_failures"
$failureCount = 0
if (Test-Path $failureDir) {
    Get-ChildItem $failureDir -File -Filter "failures.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $failureCount += (Get-Content $_.FullName -Tail 20 -ErrorAction SilentlyContinue | Where-Object { $_ }).Count
    }
}
$qualityScore -= [math]::Min(30, $failureCount * 5)
if ($localMdUpdated) { $qualityScore += 10 }
if ($evolved) { $qualityScore += 10 }
if ($settingsModified) { $qualityScore += 5 }
$qualityScore = [math]::Max(0, [math]::Min(100, $qualityScore))

$trendFile = "$summaryDir\quality_trend.jsonl"
@{ timestamp = (Get-Date -Format "o"); score = $qualityScore; friction = $frictionCount; failures = $failureCount; evolved = $evolved; sedimentation = $localMdUpdated } |
    ConvertTo-Json -Compress | Add-Content $trendFile -Encoding UTF8

# Keep last 20 summaries
Get-ChildItem $summaryDir -File -Filter "session_*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Clean echo state
Remove-Item "$baseDir\.claude\echo_state.json" -Force -ErrorAction SilentlyContinue

# Rotate friction events (keep last 50)
if (Test-Path $frictionDir) {
    Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $lines = @(Get-Content $_.FullName -Encoding UTF8 -ErrorAction SilentlyContinue)
        if ($lines.Count -gt 50) { $lines[-50..-1] | Set-Content $_.FullName -Encoding UTF8 }
    }
}

# Clean temp test files
$tmpPatterns = @("test_broken*.json", "test_broken*.ps1", "test_broken*.py", "test_final*.json")
foreach ($p in $tmpPatterns) {
    Get-ChildItem $env:TEMP -Filter $p -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-1) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-PerfLog 0; exit 0
