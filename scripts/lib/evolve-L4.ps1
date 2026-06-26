# evolve-L4.ps1 — Session archiving + cross-session pattern extraction
# Sourced by evolve.ps1; appends to $script:applied and $script:changes
param()

$archiveDir = "$env:USERPROFILE\.claude\.claude\session_archive"
$memoryDir = "$env:USERPROFILE\.claude\projects\C--Users-$env:USERNAME--claude\memory"
if (-not (Test-Path $memoryDir)) {
    $memoryDir = Get-ChildItem "$env:USERPROFILE\.claude\projects" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "memory" } |
        Where-Object { Test-Path (Join-Path $_ "MEMORY.md") } |
        Select-Object -First 1
}
if (-not $memoryDir) { return }

$now = Get-Date

# ── L4a: Archive old session logs ──
$handoffDir = "$env:USERPROFILE\.claude\.claude"
$handoffFile = Join-Path $handoffDir "handoff.md"
$qualityTrend = Join-Path $handoffDir "session_history\quality_trend.jsonl"

if (-not (Test-Path $archiveDir)) { try { New-Item -ItemType Directory -Force $archiveDir | Out-Null } catch { return } }

# Archive handoff.md if it has substantive content
if (Test-Path $handoffFile) {
    $handoffContent = Get-Content $handoffFile -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($handoffContent -and $handoffContent.Trim().Length -gt 30) {
        $ts = $now.ToString("yyyyMMdd_HHmmss")
        $archiveFile = Join-Path $archiveDir "handoff_$ts.md"
        $handoffContent | Set-Content $archiveFile -Encoding UTF8
        # Clear handoff for next session
        "HANDOFF $($now.ToString('HH:mm')) St:0 E:0 Clean" | Set-Content $handoffFile -Encoding UTF8
        $script:applied += "L4a: archived handoff.md → $archiveFile"
    }
}

# Trim old archives (>90 days)
Get-ChildItem $archiveDir -File -Filter "handoff_*.md" -ErrorAction SilentlyContinue |
    Where-Object { ($now - $_.LastWriteTime).TotalDays -gt 90 } |
    ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }

# ── L4b: Cross-session quality trend → memory principles ──
if (Test-Path $qualityTrend) {
    $sessions = Get-Content $qualityTrend -Tail 20 -Encoding UTF8 -ErrorAction SilentlyContinue |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
        Where-Object { $_ -and $_.timestamp }

    if ($sessions.Count -ge 5) {
        $scores = @($sessions | ForEach-Object { [int]$_.score })
        $avgScore = ($scores | Measure-Object -Average).Average
        $minScore = ($scores | Measure-Object -Minimum).Minimum
        $maxScore = ($scores | Measure-Object -Maximum).Maximum

        # Declining trend: 3+ sessions with score < 70
        $lowSessions = @($scores | Where-Object { $_ -lt 70 })
        if ($lowSessions.Count -ge 3) {
            $script:changes += "L4b: quality declining — $($lowSessions.Count)/$($scores.Count) sessions <70 (avg $([int]$avgScore))"
        }

        # Improving trend: last 3 sessions all > avg
        $last3 = $scores[-3..-1]
        if ($last3.Count -eq 3 -and ($last3 | Where-Object { $_ -ge $avgScore }).Count -eq 3) {
            $script:applied += "L4b: quality improving — last 3 sessions above avg ($([int]$avgScore))"
        }
    }
}

# ── L4c: Extract reusable patterns from recent sessions → memory ──
$packedDir = "$env:USERPROFILE\.claude\packed"
if (Test-Path $packedDir) {
    $recentPacks = Get-ChildItem $packedDir -File -Filter "*.json" -ErrorAction SilentlyContinue |
        Where-Object { ($now - $_.LastWriteTime).TotalDays -lt 7 } |
        Sort-Object LastWriteTime -Descending

    if ($recentPacks.Count -ge 5) {
        $patternFile = Join-Path $memoryDir "leaf" "ins-$($now.ToString('yyyyMMdd'))-cross-session-patterns.md"
        if (-not (Test-Path $patternFile)) {
            $allTags = @{}
            foreach ($pack in $recentPacks) {
                try {
                    $data = Get-Content $pack.FullName -Raw | ConvertFrom-Json
                    if ($data.tags) {
                        foreach ($tag in $data.tags) {
                            if (-not $allTags[$tag]) { $allTags[$tag] = 0 }; $allTags[$tag]++
                        }
                    }
                } catch {}
            }
            $topTags = $allTags.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 5
            if ($topTags.Count -ge 3) {
                $tagList = ($topTags | ForEach-Object { "$($_.Name)($($_.Value))" }) -join ", "
                $yaml = @"
---
name: ins-$($now.ToString('yyyyMMdd'))-cross-session
description: Cross-session pattern: top tags from $($recentPacks.Count) recent sessions
metadata:
  type: insight
created: $($now.ToString('yyyy-MM-dd'))
---

# Cross-Session Patterns — $($now.ToString('yyyy-MM-dd'))

Top recurring tags across $($recentPacks.Count) sessions (7 days):
$tagList

**Why:** These patterns span multiple sessions, indicating systemic behavior.
**How to apply:** Prioritize improvements related to these areas.
"@
                $yaml | Set-Content $patternFile -Encoding UTF8
                $script:applied += "L4c: cross-session pattern extracted ($($recentPacks.Count) sessions, top: $tagList)"
            }
        }
    }
}

# ── L4d: Dead session data cleanup (>90 days) ──
$cleanupDirs = @($archiveDir, $packedDir)
foreach ($dir in $cleanupDirs) {
    if (-not (Test-Path $dir)) { continue }
    $oldFiles = Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { ($now - $_.LastWriteTime).TotalDays -gt 90 }
    if ($oldFiles.Count -gt 0) {
        $oldFiles | ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }
        $script:changes += "L4d: cleaned $($oldFiles.Count) archived files >90 days from $dir"
    }
}
