# session-end.ps1 — SessionEnd: final cleanup + session summary
param()

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$summaryDir = "$env:USERPROFILE\.claude\.claude\session_history"
if (-not (Test-Path $summaryDir)) { New-Item -ItemType Directory -Force $summaryDir | Out-Null }

# Collect what happened this session
$perfDir = "$env:USERPROFILE\.claude\.claude\hook_perf"
$frictionDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"
$successFile = "$env:USERPROFILE\.claude\.claude\last_session_success.json"
$settingsJson = "$env:USERPROFILE\.claude\settings.json"
$localMd = "$env:USERPROFILE\.claude\CLAUDE.local.md"

# Hook activity count
$hookActivity = @{}
if (Test-Path $perfDir) {
    Get-ChildItem $perfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $count = (Get-Content $_.FullName -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ }).Count
        $hookActivity[$_.BaseName] = $count
    }
}

# Friction count this session
$frictionCount = 0
if (Test-Path $frictionDir) {
    Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $frictionCount += (Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue | Where-Object { $_ }).Count
    }
}

# Did we evolve?
$evolved = $false
$evolveLog = "$env:USERPROFILE\.claude\.claude\evolution_log.jsonl"
if (Test-Path $evolveLog) {
    $lastLine = Get-Content $evolveLog -Tail 1 -ErrorAction SilentlyContinue
    if ($lastLine) {
        try {
            $lastEvo = $lastLine | ConvertFrom-Json
            $evolved = ([datetime]$lastEvo.timestamp) -gt (Get-Date).AddHours(-2)
        } catch { }
    }
}

# Was CLAUDE.local.md updated?
$localMdUpdated = (Get-Item $localMd).LastWriteTime -gt (Get-Date).AddHours(-2)

# Settings modified?
$settingsModified = (Get-Item $settingsJson).LastWriteTime -gt (Get-Date).AddHours(-2)

# Write summary
$summary = @{
    timestamp = (Get-Date -Format "o")
    hook_calls = $hookActivity
    friction_events = $frictionCount
    evolved = $evolved
    sedimentation = $localMdUpdated
    settings_modified = $settingsModified
    success = if (Test-Path $successFile) { try { Get-Content $successFile -Raw | ConvertFrom-Json } catch { $null } } else { $null }
}

$summaryFile = Join-Path $summaryDir "session_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
$summary | ConvertTo-Json -Depth 3 | Set-Content $summaryFile -Encoding UTF8

# ── Session quality score ──
$qualityScore = 100
$qualityScore -= [math]::Min(50, $frictionCount * 10)
$failureDir = "$env:USERPROFILE\.claude\.claude\tool_failures"
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
$summary | Add-Member -NotePropertyName quality_score -NotePropertyValue $qualityScore -Force

# Append to quality trend
$trendFile = "$summaryDir\quality_trend.jsonl"
@{ timestamp = (Get-Date -Format "o"); score = $qualityScore; friction = $frictionCount; failures = $failureCount; evolved = $evolved; sedimentation = $localMdUpdated } |
    ConvertTo-Json -Compress | Add-Content $trendFile -Encoding UTF8

# Keep only last 20 summaries
Get-ChildItem $summaryDir -File -Filter "session_*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 20 |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Clean echo state
Remove-Item "$env:USERPROFILE\.claude\.claude\echo_state.json" -Force -ErrorAction SilentlyContinue

# Rotate tellonce friction events (keep last 50)
$tellonceDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"
if (Test-Path $tellonceDir) {
    Get-ChildItem $tellonceDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
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

exit 0
