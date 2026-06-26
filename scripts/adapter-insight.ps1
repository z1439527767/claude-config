# adapter-insight.ps1 — Pattern analyzer for evolution/friction/error data
# Surfaces actionable insights from accumulated session data.
# Usage:
#   adapter-insight.ps1 -Friction    → friction pattern analysis
#   adapter-insight.ps1 -Failures    → tool failure pattern analysis
#   adapter-insight.ps1 -Evolution   → evolution effectiveness analysis
#   adapter-insight.ps1 -All         → full insight report
#   adapter-insight.ps1 -TopN 5      → top N issues to fix now
param([switch]$Friction, [switch]$Failures, [switch]$Evolution, [switch]$All, [int]$TopN = 5)
$ErrorActionPreference = "Continue"
$baseDir = "$env:USERPROFILE\.claude"
. "$baseDir\scripts\lib\dblog.ps1"

$ErrorActionPreference = "Continue"
$baseDir = "$env:USERPROFILE\.claude"

function Get-JsonLines($path) {
    # Fallback: read from JSONL file (used when DB unavailable)
    if (Test-Path $path) {
        Get-Content $path -ErrorAction SilentlyContinue | Where-Object { $_ -ne "" } | ForEach-Object {
            try { $_ | ConvertFrom-Json } catch { $null }
        }
    }
}

function Get-Events($source, [int]$tail = 500) {
    # SQLite-first, JSONL fallback
    $dbResult = Read-DbLog -Source $source -Tail $tail -AsJson
    if ($dbResult) { return $dbResult }
    # Map source to JSONL path for fallback
    $paths = @{
        "friction/events" = "$baseDir\.claude\tellonce-state\friction\events.jsonl"
        "tool_failures" = "$baseDir\.claude\tool_failures\failures.jsonl"
        "evolution_log" = "$baseDir\.claude\evolution_log.jsonl"
    }
    $path = $paths[$source]
    if ($path) { return @(Get-JsonLines $path) }
    return @()
}

# ═══ Friction Analysis ═══
if ($Friction -or $All) {
    Write-Output "═══ FRICTION PATTERNS ═══`n"
    $events = Get-Events "friction/events"

    if ($events.Count -eq 0) {
        Write-Output "  No friction events recorded.`n"
    } else {
        # Extract signals
        $signals = @{}
        foreach ($e in $events) {
            if ($e.signals) {
                foreach ($s in ($e.signals -split ',\s*')) {
                    $signals[$s] = [int]$signals[$s] + 1
                }
            }
        }

        Write-Output "  Total events: $($events.Count)"
        Write-Output "  Last event:   $($events[-1].timestamp)"
        Write-Output "  Top signals:"
        foreach ($s in ($signals.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First $TopN)) {
            Write-Output "    $($s.Key): $($s.Value)x"
        }

        # Time-based pattern
        $byDay = $events | Group-Object { ([datetime]$_.timestamp).ToString("yyyy-MM-dd") }
        Write-Output "`n  By day:"
        foreach ($d in $byDay) { Write-Output "    $($d.Name): $($d.Count) events" }
        Write-Output ""
    }
}

# ═══ Failure Analysis ═══
if ($Failures -or $All) {
    Write-Output "═══ TOOL FAILURE PATTERNS ═══`n"
    $failures = @(Get-Events "tool_failures")

    if ($failures.Count -eq 0) {
        Write-Output "  No tool failures recorded.`n"
    } else {
        $byTool = $failures | Group-Object tool
        Write-Output "  Total failures: $($failures.Count)"
        foreach ($t in ($byTool | Sort-Object Count -Descending | Select-Object -First $TopN)) {
            Write-Output "    $($t.Name): $($t.Count)x"
            $lastErr = $t.Group[-1].error
            if ($lastErr) { Write-Output "      Last: $($lastErr.Substring(0, [math]::Min(80, $lastErr.Length)))" }
        }
        Write-Output ""
    }
}

# ═══ Evolution Effectiveness ═══
if ($Evolution -or $All) {
    Write-Output "═══ EVOLUTION EFFECTIVENESS ═══`n"
    $evos = Get-Events "evolution_log"

    if ($evos.Count -eq 0) {
        Write-Output "  No evolution events recorded.`n"
    } else {
        $totalChanges = ($evos | ForEach-Object { $_.changes.Count } | Measure-Object -Sum).Sum
        $l1l2 = ($evos | ForEach-Object { ($_.changes | Where-Object { $_ -match '^L[12]:' }).Count } | Measure-Object -Sum).Sum
        $l3 = ($evos | ForEach-Object { ($_.changes | Where-Object { $_ -match '^L3' }).Count } | Measure-Object -Sum).Sum
        $l4l5 = ($evos | ForEach-Object { ($_.changes | Where-Object { $_ -match '^L[45]:' }).Count } | Measure-Object -Sum).Sum

        Write-Output "  Total cycles:    $($evos.Count)"
        Write-Output "  Total changes:   $totalChanges"
        Write-Output "  L1+L2 (rules):   $l1l2"
        Write-Output "  L3 (timeouts):   $l3"
        Write-Output "  L4+L5 (cleanup): $l4l5"

        # Pattern: what kind of changes dominate?
        Write-Output "`n  Dominant layer: $(if ($l3 -gt $l1l2 -and $l3 -gt $l4l5) { 'L3 (timeout tuning) — consider adding more L1/L2 rule evolutions' } elseif ($l1l2 -gt $l3) { 'L1+L2 (rule evolution) — healthy' } else { 'Balanced' })"

        # Recent trend
        $recent = $evos | Where-Object { [datetime]$_.timestamp -gt (Get-Date).AddHours(-6) }
        Write-Output "  Last 6h:         $($recent.Count) cycles, $(($recent | ForEach-Object { $_.changes.Count } | Measure-Object -Sum).Sum) changes"
        Write-Output ""
    }
}

# ═══ Top Issues ═══
if ($All) {
    Write-Output "═══ TOP $TopN ISSUES TO FIX ═══`n"
    $issues = @()

    # Check for repeated failures
    $failures = @(Get-Events "tool_failures")
    if ($failures.Count -gt 0) {
        $byTool = $failures | Group-Object tool | Sort-Object Count -Descending
        foreach ($t in $byTool | Select-Object -First 2) {
            $issues += @{ severity = "HIGH"; issue = "$($t.Name) failed $($t.Count)x — investigate root cause" }
        }
    }

    # Check for stale memory
    $memIndex = Get-ChildItem "$baseDir\projects" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "memory\MEMORY.md" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
    if (Test-Path $memIndex) {
        $aging = @(Get-Content $memIndex -Encoding UTF8 | Where-Object { $_ -match 'aging|stale' })
        if ($aging.Count -gt 0) {
            $issues += @{ severity = "MEDIUM"; issue = "$($aging.Count) aging/stale memories — run consolidation" }
        }
    }

    # Check for slow hooks
    $perfDir = "$baseDir\.claude\hook_perf"
    if (Test-Path $perfDir) {
        $slow = Get-ChildItem $perfDir -File -Filter "*.jsonl" | ForEach-Object {
            $last = Get-Content $_.FullName -Tail 3 | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } }
            $avg = ($last | Where-Object { $_.duration_ms } | Measure-Object -Property duration_ms -Average).Average
            if ($avg -gt 3000) { @{ hook = $_.BaseName; avg_ms = [math]::Round($avg) } }
        }
        foreach ($s in ($slow | Select-Object -First 3)) {
            $issues += @{ severity = "MEDIUM"; issue = "$($s.hook) avg ${$s.avg_ms}ms — consider optimizing" }
        }
    }

    # Check for gated evolution
    $evoGate = "$baseDir\.claude\evo_gate.json"
    if (Test-Path $evoGate) {
        try {
            $gate = Get-Content $evoGate -Raw | ConvertFrom-Json
            $recentCount = @($gate.recent_evo_timestamps | Where-Object { [datetime]$_ -gt (Get-Date).AddDays(-7) }).Count
            if ($recentCount -ge 10) {
                $issues += @{ severity = "LOW"; issue = "Evolution gated (10 in 7 days) — will clear automatically" }
            }
        } catch {}
    }

    # No issues found
    if ($issues.Count -eq 0) {
        Write-Output "  ✅ No issues detected"
    } else {
        $rank = 1
        foreach ($i in ($issues | Select-Object -First $TopN)) {
            Write-Output "  ${rank}. [$($i.severity)] $($i.issue)"
            $rank++
        }
    }
    Write-Output ""
}
