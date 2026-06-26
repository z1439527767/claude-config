# metacog-bridge.ps1 — SessionEnd: extract behavioral learnings → metacog pipeline
# Split from 304→80 lines. Detectors in lib/metacog-detect.ps1
param()
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$perfHookName = "metacog-bridge"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "metacog-bridge" -EntityName "hook-metacog-bridge-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("metacog-bridge executed at $(Get-Date -Format 'o')") -Priority "low"
$now = Get-Date
$projDir = "$env:USERPROFILE\.claude"
$learningsGlobal = "$env:USERPROFILE\.claude\metacog-learnings.jsonl"
$learningsProject = "$projDir\.claude\metacog-learnings.jsonl"
$frictionDir = "$projDir\.claude\tellonce-state\friction"
$evolveLog = "$projDir\.claude\evolution_log.jsonl"

$script:learnings = @()

# ── Source 1: metacog state → behavioral detectors ──
$stateFile = "$projDir\.claude\metacog.state.json"
if (Test-Path $stateFile) {
    try { $state = Get-Content $stateFile -Raw | ConvertFrom-Json } catch { $state = $null }
    if ($state -and $state.actions) {
        $tc = if ($state.turn_count) { [int]$state.turn_count } else { 0 }
        . "$env:USERPROFILE\.claude\scripts\lib\metacog-detect.ps1" -actions @($state.actions) -turnCount $tc -now $now
    }
}

# ── Source 2: Friction events → behavioral patterns ──
if (Test-Path $frictionDir) {
    $allFriction = Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue |
        ForEach-Object { Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue | Where-Object { $_ } |
            ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ } }
    $recentFriction = $allFriction | Where-Object { $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-1) }
    if ($recentFriction.Count -ge 3) {
        $catCounts = @{}
        foreach ($f in $recentFriction) {
            $cats = if ($f.categories -is [array]) { $f.categories } else { @($f.categories -split ', ') }
            foreach ($c in $cats) {
                if (-not $catCounts[$c]) { $catCounts[$c] = 0 }
                $catCounts[$c]++
            }
        }
        $topCat = ($catCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1)
        if ($topCat.Value -ge 3) {
            $catLessonMap = @{
                "correction" = "Frequent user corrections detected. Check CLAUDE.md rules for gaps."
                "recurrence" = "Same issues recurring — previous fixes didn't address root cause."
                "stop" = "User frequently issuing stop signals — agent may be over-executing."
                "retry" = "Frequent retries indicate first attempts are low quality."
                "negation" = "Directional corrections accumulating — understanding of user intent may be off."
                "simplify" = "Output is consistently too complex. Default to minimal replies."
                "slow" = "Perceived slowness. Optimize parallelism, reduce unnecessary tool calls."
                "noise" = "Hook output is too noisy. Audit hooks for excessive stdout."
            }
            $lesson = if ($catLessonMap.ContainsKey($topCat.Name)) { $catLessonMap[$topCat.Name] } else { "Friction category '$($topCat.Name)' triggered $($topCat.Value) times in 24h." }
            $script:learnings += @{
                pattern = "friction_$($topCat.Name)"; type = "detection"; category = "User Friction"
                lesson = $lesson; detected_at = $now.ToString("o"); session_turn_count = if ($state -and $state.turn_count) { [int]$state.turn_count } else { 0 }
            }
        }
    }
}

# ── Source 3: Evolution activity ──
if (Test-Path $evolveLog) {
    $todayEvos = Get-Content $evolveLog -Tail 5 -Encoding UTF8 -ErrorAction SilentlyContinue |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
        Where-Object { $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-1) }
    $l1Count = ($todayEvos | ForEach-Object { $_.changes } | Where-Object { $_ -match "L1:" }).Count
    $l2Count = ($todayEvos | ForEach-Object { $_.changes } | Where-Object { $_ -match "L2:" }).Count
    $l3Count = ($todayEvos | ForEach-Object { $_.changes } | Where-Object { $_ -match "L3:" }).Count
    if (($l1Count + $l2Count + $l3Count) -ge 3) {
        $script:learnings += @{
            pattern = "active_evolution"; type = "detection"; category = "Self-Evolution"
            lesson = "Evolution active: L1=$l1Count L2=$l2Count L3=$l3Count in 24h."
            detected_at = $now.ToString("o"); session_turn_count = if ($state -and $state.turn_count) { [int]$state.turn_count } else { 0 }
        }
    }
}

# ── Dedup + persist ──
$existingPatterns = @{}
foreach ($path in @($learningsGlobal, $learningsProject)) {
    if (Test-Path $path) {
        Get-Content $path -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ } |
            ForEach-Object { try { $l = $_ | ConvertFrom-Json; $existingPatterns[$l.pattern] = $true } catch {} }
    }
}
$newLearnings = $script:learnings | Where-Object { -not $existingPatterns[$_.pattern] }

if ($newLearnings.Count -gt 0) {
    $lines = ($newLearnings | ForEach-Object { $_ | ConvertTo-Json -Compress }) -join "`n"
    foreach ($dir in (Split-Path $learningsGlobal -Parent), (Split-Path $learningsProject -Parent)) {
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    }
    Add-Content -Path $learningsGlobal -Value $lines -Encoding UTF8
    Add-Content -Path $learningsProject -Value $lines -Encoding UTF8
    $patterns = ($newLearnings | ForEach-Object { $_.pattern }) -join ", "
    Write-Output "METACOG: $($newLearnings.Count) learnings persisted: $patterns"
} else {
    Write-Output "METACOG: no new learnings (all patterns already known)"
}

Write-PerfLog 0; exit 0
