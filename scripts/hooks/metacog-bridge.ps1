# metacog-bridge.ps1 — SessionEnd: extract behavioral learnings → metacog pipeline
# Bridges custom hooks (friction, evolve, auto-verify) with @houtini/metacog's learning system
# Writes to metacog-learnings.jsonl so digest-inject.js compiles them next session
param()
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$perfHookName = "metacog-bridge"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$now = Get-Date
$homedir = $env:USERPROFILE
$projDir = "$homedir\.claude"
$stateFile = "$projDir\.claude\metacog.state.json"
$learningsGlobal = "$homedir\.claude\metacog-learnings.jsonl"
$learningsProject = "$projDir\.claude\metacog-learnings.jsonl"
$frictionDir = "$projDir\.claude\tellonce-state\friction"
$evolveLog = "$projDir\.claude\evolution_log.jsonl"
$successFile = "$projDir\.claude\last_session_success.json"

$learnings = @()

# ═══════════════════════════════════════
# Source 1: metacog state → built-in detectors
# ═══════════════════════════════════════
if (Test-Path $stateFile) {
    try { $state = Get-Content $stateFile -Raw | ConvertFrom-Json } catch { $state = $null }
    if ($state -and $state.actions) {
        $actions = @($state.actions)
        $turnCount = $state.turn_count ?? $actions.Count

        # ── Detector: circular_search (3+ consecutive reads) ──
        $consecutiveReads = 0; $maxConsecutiveReads = 0
        foreach ($a in $actions) {
            if ($a.action_type -eq 'read') { $consecutiveReads++; $maxConsecutiveReads = [Math]::Max($maxConsecutiveReads, $consecutiveReads) }
            else { $consecutiveReads = 0 }
        }
        if ($maxConsecutiveReads -ge 3) {
            $learnings += @{
                pattern = "circular_search"
                type = "detection"
                category = "Search Patterns"
                lesson = "When searching for a pattern, use one broad Grep before narrowing. Multiple sequential read calls on the same target signals thrashing."
                detected_at = $now.ToString("o")
                session_turn_count = $turnCount
            }
        }

        # ── Detector: repeated_file_read (same file 3+ times) ──
        $readCounts = @{}
        foreach ($a in $actions) {
            if ($a.tool_name -eq 'Read' -and $a.target_resource -and $a.target_resource -ne 'unknown') {
                if (-not $readCounts[$a.target_resource]) { $readCounts[$a.target_resource] = 0 }
                $readCounts[$a.target_resource]++
            }
        }
        $repeats = $readCounts.GetEnumerator() | Where-Object { $_.Value -ge 3 }
        if ($repeats) {
            $learnings += @{
                pattern = "repeated_file_read"
                type = "detection"
                category = "File Access"
                lesson = "Files read 3+ times per session should be summarised to a scratchpad early. Context compaction deletes the content but not the need for it."
                detected_at = $now.ToString("o")
                session_turn_count = $turnCount
            }
        }

        # ── Detector: error_loop (4+ errors in last 10, ≤2 unique sigs) ──
        $recentErrors = $actions | Select-Object -Last 10 | Where-Object { $_.exit_status -eq 'error' }
        if ($recentErrors.Count -ge 4) {
            $sigs = $recentErrors | ForEach-Object { $_.error_signature } | Where-Object { $_ }
            $uniqueSigs = ($sigs | Select-Object -Unique).Count
            if ($uniqueSigs -le 2 -and $sigs.Count -ge 3) {
                $learnings += @{
                    pattern = "error_loop"
                    type = "detection"
                    category = "Error Handling"
                    lesson = "When hitting the same error 3+ times, stop and diagnose the root cause rather than retrying. Check assumptions about paths, APIs, and environment."
                    detected_at = $now.ToString("o")
                    session_turn_count = $turnCount
                }
            }
        }

        # ── Detector: long_autonomous_run (>30 turns without user) ──
        if ($turnCount -gt 30) {
            $learnings += @{
                pattern = "long_autonomous_run"
                type = "detection"
                category = "Autonomy"
                lesson = "Sessions exceeding 30 tool calls should delegate independent work to background agents earlier. Context pressure increases with every call."
                detected_at = $now.ToString("o")
                session_turn_count = $turnCount
            }
        }

        # ── Detector: write_heavy_session (writes > reads) ──
        $writeCount = ($actions | Where-Object { $_.action_type -eq 'write' }).Count
        $readCount = ($actions | Where-Object { $_.action_type -eq 'read' }).Count
        if ($writeCount -gt 8 -and $readCount -lt $writeCount * 0.5) {
            $learnings += @{
                pattern = "write_heavy_session"
                type = "detection"
                category = "Code Quality"
                lesson = "High write-to-read ratio suggests editing without sufficient context. Read before writing — especially files you haven't seen this session."
                detected_at = $now.ToString("o")
                session_turn_count = $turnCount
            }
        }

        # ── Detector: read_before_edit_violation (wrote without prior read) ──
        $readTargets = @{}
        foreach ($a in $actions) {
            if ($a.action_type -eq 'read' -and $a.target_resource -and $a.target_resource -ne 'unknown') {
                $readTargets[$a.target_resource] = $true
            }
        }
        $writesWithoutRead = @()
        foreach ($a in $actions) {
            if ($a.action_type -eq 'write' -and $a.target_resource -and $a.target_resource -ne 'unknown') {
                if (-not $readTargets[$a.target_resource]) {
                    $fname = Split-Path $a.target_resource -Leaf
                    if ($fname -notin $writesWithoutRead) { $writesWithoutRead += $fname }
                }
            }
        }
        if ($writesWithoutRead.Count -ge 3) {
            $learnings += @{
                pattern = "read_before_edit_violation"
                type = "detection"
                category = "Code Quality"
                lesson = "$($writesWithoutRead.Count) files edited without being read first. Always read before editing to avoid overwriting changes or working from stale context."
                detected_at = $now.ToString("o")
                session_turn_count = $turnCount
            }
        }

        # ── Detector: mono_tool (80%+ same tool in last 15 actions) ──
        $recent15 = @($actions | Select-Object -Last 15)
        if ($recent15.Count -ge 10) {
            $toolCounts = @{}
            foreach ($a in $recent15) { if (-not $toolCounts[$a.tool_name]) { $toolCounts[$a.tool_name] = 0 }; $toolCounts[$a.tool_name]++ }
            $maxTool = ($toolCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1)
            if ($maxTool.Value -ge $recent15.Count * 0.8) {
                $learnings += @{
                    pattern = "mono_tool_dominance"
                    type = "detection"
                    category = "Action Patterns"
                    lesson = "$($maxTool.Value)/$($recent15.Count) recent actions used '$($maxTool.Name)'. Over-reliance on one tool type suggests tunnel vision — consider whether a different approach would be faster."
                    detected_at = $now.ToString("o")
                    session_turn_count = $turnCount
                }
            }
        }
    }
}

# ═══════════════════════════════════════
# Source 2: Friction events → behavioral patterns
# ═══════════════════════════════════════
if (Test-Path $frictionDir) {
    $allFriction = Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue | Where-Object { $_ } |
                ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ }
        }

    $recentFriction = $allFriction | Where-Object {
        $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-1)
    }

    if ($recentFriction.Count -ge 3) {
        $catCounts = @{}
        foreach ($f in $recentFriction) {
            foreach ($c in ($f.categories -split ', ')) {
                if (-not $catCounts[$c]) { $catCounts[$c] = 0 }; $catCounts[$c]++
            }
        }
        $topCat = ($catCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1)
        if ($topCat.Value -ge 3) {
            $catLessonMap = @{
                "correction" = "Frequent user corrections detected. Check CLAUDE.md rules for gaps — something the user expects isn't encoded."
                "recurrence" = "Same issues recurring — previous fixes didn't address root cause. When fixing, ask: what SYSTEMIC change prevents this class of error?"
                "stop" = "User frequently issuing stop signals — agent may be over-executing or heading in wrong direction. Ask clarifying questions earlier."
                "retry" = "Frequent retries indicate first attempts are low quality. Slow down and verify assumptions before acting."
                "negation" = "Directional corrections accumulating — understanding of user intent may be systematically off."
                "simplify" = "Output is consistently too complex. Default to minimal replies with optional expansion."
                "slow" = "Perceived slowness. Optimize parallelism, reduce unnecessary tool calls."
                "noise" = "Hook output is too noisy. Audit hooks for excessive stdout."
            }
            $lesson = $catLessonMap[$topCat.Name] ?? "Friction category '$($topCat.Name)' triggered $($topCat.Value) times in 24h — review and adjust."
            $learnings += @{
                pattern = "friction_$($topCat.Name)"
                type = "detection"
                category = "User Friction"
                lesson = $lesson
                detected_at = $now.ToString("o")
                session_turn_count = ($state.turn_count ?? 0)
            }
        }
    }
}

# ═══════════════════════════════════════
# Source 3: Evolution log → learning from what changed
# ═══════════════════════════════════════
if (Test-Path $evolveLog) {
    $todayEvos = Get-Content $evolveLog -Tail 5 -Encoding UTF8 -ErrorAction SilentlyContinue |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
        Where-Object { $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-1) }

    $l1Count = ($todayEvos | ForEach-Object { $_.changes } | Where-Object { $_ -match "L1:" }).Count
    $l2Count = ($todayEvos | ForEach-Object { $_.changes } | Where-Object { $_ -match "L2:" }).Count
    $l3Count = ($todayEvos | ForEach-Object { $_.changes } | Where-Object { $_ -match "L3:" }).Count

    if (($l1Count + $l2Count + $l3Count) -ge 3) {
        $learnings += @{
            pattern = "active_evolution"
            type = "detection"
            category = "Self-Evolution"
            lesson = "Evolution is active: L1=$l1Count L2=$l2Count L3=$l3Count in 24h. System is learning — ensure new rules are tested for effectiveness."
            detected_at = $now.ToString("o")
            session_turn_count = ($state.turn_count ?? 0)
        }
    }
}

# ═══════════════════════════════════════
# Source 4: Session quality trends → meta-meta-cognition
# ═══════════════════════════════════════
$trendFile = "$projDir\.claude\session_history\quality_trend.jsonl"
if (Test-Path $trendFile) {
    $trends = Get-Content $trendFile -Tail 10 -Encoding UTF8 -ErrorAction SilentlyContinue |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ }
    if ($trends.Count -ge 3) {
        $scores = $trends | ForEach-Object { $_.score }
        $avgScore = ($scores | Measure-Object -Average).Average
        $trend = if ($trends.Count -ge 2) {
            $last = $trends[-1].score; $prev = $trends[-2].score
            if ($last -lt $prev - 10) { "declining" } elseif ($last -gt $prev + 10) { "improving" } else { "stable" }
        } else { "insufficient_data" }

        if ($trend -eq "declining") {
            $learnings += @{
                pattern = "quality_declining"
                type = "detection"
                category = "Session Quality"
                lesson = "Session quality score declining (avg $([int]$avgScore)). Investigate rising friction or failure rates."
                detected_at = $now.ToString("o")
                session_turn_count = ($state.turn_count ?? 0)
            }
        }
        if ($avgScore -lt 60) {
            $learnings += @{
                pattern = "quality_low"
                type = "detection"
                category = "Session Quality"
                lesson = "Average session quality score is $([int]$avgScore)/100. Root causes: check friction events and tool failure logs."
                detected_at = $now.ToString("o")
                session_turn_count = ($state.turn_count ?? 0)
            }
        }
    }
}

# ═══════════════════════════════════════
# Dedup: merge with existing learnings
# ═══════════════════════════════════════
$existingPatterns = @{}
foreach ($path in @($learningsGlobal, $learningsProject)) {
    if (Test-Path $path) {
        Get-Content $path -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ } |
            ForEach-Object { try { $l = $_ | ConvertFrom-Json; $existingPatterns[$l.pattern] = $true } catch {} }
    }
}

$newLearnings = $learnings | Where-Object { -not $existingPatterns[$_.pattern] }

# ═══════════════════════════════════════
# Persist to JSONL (both global + project)
# ═══════════════════════════════════════
if ($newLearnings.Count -gt 0) {
    $lines = ($newLearnings | ForEach-Object { $_ | ConvertTo-Json -Compress }) -join "`n"

    # Global
    $globalDir = Split-Path $learningsGlobal -Parent
    if (-not (Test-Path $globalDir)) { New-Item -ItemType Directory -Force $globalDir | Out-Null }
    Add-Content -Path $learningsGlobal -Value $lines -Encoding UTF8

    # Project-scoped
    $projLearnDir = Split-Path $learningsProject -Parent
    if (-not (Test-Path $projLearnDir)) { New-Item -ItemType Directory -Force $projLearnDir | Out-Null }
    Add-Content -Path $learningsProject -Value $lines -Encoding UTF8

    # Digest compilation runs via digest-inject.js on next session start.
    # The learnings.jsonl has been updated; metacog will pick it up automatically.

    $patterns = ($newLearnings | ForEach-Object { $_.pattern }) -join ", "
    Write-Output "METACOG: $($newLearnings.Count) learnings persisted: $patterns"
} else {
    Write-Output "METACOG: no new learnings (all patterns already known)"
}

Write-PerfLog 0; exit 0
