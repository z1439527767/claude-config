# memory-score.ps1 — Ebbinghaus memory scoring (standalone)
# Can be run directly: pwsh -ExecutionPolicy Bypass -File memory-score.ps1
# Or called from other hooks: & pwsh -File "...memory-score.ps1"
param(
    [string]$MemoryDir = "$env:USERPROFILE\.claude\projects\C--Users-z1439--claude\memory",
    [string]$StateFile = "$env:USERPROFILE\.claude\.claude\memory_scores.json"
)

$ErrorActionPreference = "Continue"
$perfHookName = "memory-score"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$memIndex = Join-Path $MemoryDir "MEMORY.md"
if (-not (Test-Path $memIndex)) { Write-Output "memory-score: MEMORY.md not found at $memIndex"; Write-PerfLog 0; return }

$state = @{}
if (Test-Path $StateFile) {
    try {
        $raw = Get-Content $StateFile -Raw -Encoding UTF8 -ErrorAction Stop
        $parsed = $raw | ConvertFrom-Json
        foreach ($prop in $parsed.PSObject.Properties) {
            $state[$prop.Name] = @{
                access_count         = [int]   $prop.Value.access_count
                last_access          = [string]$prop.Value.last_access
                applied_successfully = [bool]  $prop.Value.applied_successfully
            }
        }
    } catch { $state = @{} }
}

$memContent = Get-Content $memIndex -Raw -Encoding UTF8
$lines = $memContent -split "`n"
$entries = @()

for ($i = 0; $i -lt $lines.Count; $i++) {
    $line = $lines[$i]
    if ($line -match '^- \[(\S+)\]\(([^)]+)\) — (.+?)\s\[.+?\]$') {
        $entries += @{
            id          = $Matches[1]
            path        = $Matches[2]
            description = $Matches[3]
            oldTag      = $Matches[4]
            lineIndex   = $i
        }
    }
}

if ($entries.Count -eq 0) { Write-Output "memory-score: no entries found"; Write-PerfLog 0; return }

$now = Get-Date
foreach ($entry in $entries) {
    $created = $null
    $memFile = Join-Path $MemoryDir $entry.path
    if (Test-Path $memFile) {
        $content = Get-Content $memFile -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($content -and $content -match '(?m)^\s*created:\s*(.+)$') { $created = $Matches[1].Trim() }
    }
    if (-not $state.ContainsKey($entry.id)) {
        $state[$entry.id] = @{ access_count = 0; last_access = $null; applied_successfully = $false }
    }
    $es = $state[$entry.id]
    $es.access_count = [int]$es.access_count + 1
    $es.last_access = $now.ToString("yyyy-MM-dd")

    $createdDt = if ($created) { try { [datetime]::ParseExact($created, "yyyy-MM-dd", $null) } catch { $now } } else { $now }
    $lastAccessDt = if ($es.last_access) { try { [datetime]::ParseExact($es.last_access, "yyyy-MM-dd", $null) } catch { $createdDt } } else { $createdDt }
    $daysSinceCreation   = [math]::Max(0, ($now - $createdDt).TotalDays)
    $daysSinceLastAccess = [math]::Max(0, ($now - $lastAccessDt).TotalDays)

    $score = [math]::Min(1.0, [math]::Exp(-$daysSinceCreation / 30) +
                                 [math]::Min([int]$es.access_count * 0.05, 0.3) +
                                 $(if ($daysSinceLastAccess -lt 7) { 0.15 } elseif ($daysSinceLastAccess -lt 30) { 0.10 } else { 0 }) +
                                 $(if ($es.applied_successfully) { 0.20 } else { 0 }))
    if ($daysSinceLastAccess -ge 60) { $score = $score * 0.5 }
    $score = [math]::Round($score, 2)

    $tag = if ($score -ge 0.8) { "fresh" } elseif ($score -ge 0.5) { "aging" } elseif ($score -ge 0.3) { "stale" } else { "expired" }
    $scoreStr = "{0:N2}" -f $score
    $lines[$entry.lineIndex] = "- [$($entry.id)]($($entry.path)) — $($entry.description) [$scoreStr $tag]"
}

$state | ConvertTo-Json -Depth 5 | Set-Content $StateFile -Encoding UTF8

# Rebuild MEMORY.md header while preserving sections
$firstSectionIdx = -1; $footerSepIdx = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($firstSectionIdx -eq -1 -and $lines[$i] -match '^## Root') { $firstSectionIdx = $i }
    if ($lines[$i] -match '^---$' -and $i -gt ($firstSectionIdx + 2)) { $footerSepIdx = $i; break }
}
if ($firstSectionIdx -eq -1) { $firstSectionIdx = $lines.Count }

$newContent = @"
# Memory

> 樹狀記憶索引。root -> branch -> leaf -> distilled。
> 總條數：$($entries.Count) / 上限 50。最後更新：$($now.ToString('yyyy-MM-dd'))。

## Scoring
Every memory carries a confidence score **[0.0 - 1.0]** recalculated each session:

| Factor | Rule |
|---|---|
| Base decay | e^(-days_since_creation / 30) (Ebbinghaus, 30-day half-life) |
| Access boost | min(access_count * 0.05, 0.3) - repeated use slows decay |
| Recency boost | +0.15 if accessed under 7 days ago, +0.10 if under 30 days |
| Success boost | +0.20 if memory was applied successfully (total capped at 1.0) |
| Accelerated decay | x0.5 if unaccessed for 60+ days |

Tags: [fresh] >= 0.8 / [aging] >= 0.5 / [stale] >= 0.3 / [expired] under 0.3

"@
$endIdx = if ($footerSepIdx -ge 0) { $footerSepIdx } else { $lines.Count }
for ($i = $firstSectionIdx; $i -lt $endIdx; $i++) { $newContent += $lines[$i] + "`n" }
$newContent += @'

---

## Score Formula
```
score = min(1.0, e^(-days/30) + min(access * 0.05, 0.3) + recency + success)
recency = days_since_access lessThan 7 ? 0.15 : lessThan 30 ? 0.10 : 0
success = applied_successfully ? 0.20 : 0
if days_since_access >= 60: score = score * 0.5
```

Tags: [fresh] >= 0.8 / [aging] >= 0.5 / [stale] >= 0.3 / [expired] under 0.3
'@
Set-Content $memIndex -Value $newContent -Encoding UTF8

Write-PerfLog 0
Write-Output "memory-score: $($entries.Count) entries scored"
