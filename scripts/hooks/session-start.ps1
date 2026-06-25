# session-start.ps1 v2 — merged: health-check + syntax + memory-score + context-inject
param()
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$sw = [Diagnostics.Stopwatch]::StartNew()

$baseDir = "$env:USERPROFILE\.claude"

# ═══════════════════════════════════════════
# PHASE 0: Health check — hook deps + key files
# ═══════════════════════════════════════════
$healthIssues = @()

# 0a. settings.json valid?
$settings = $null
try { $settings = Get-Content "$baseDir\settings.json" -Raw | ConvertFrom-Json } catch {
    Write-Output "FATAL: settings.json unreadable: $_"; exit 2
}

# 0b. Hook refs → existing scripts?
foreach ($eventName in $settings.hooks.PSObject.Properties.Name) {
    foreach ($group in $settings.hooks.$eventName) {
        foreach ($h in $group.hooks) {
            if ($h.command -match '([^\\"]+\.ps1)') {
                $sp = Join-Path "$baseDir\scripts\hooks" $Matches[1]
                if (-not (Test-Path $sp)) { $healthIssues += "hook $eventName → $($Matches[1]) missing" }
            }
        }
    }
}

# 0c. Key config files exist?
@("$baseDir\CLAUDE.md","$baseDir\AGENTS.md","$baseDir\CLAUDE.local.md") | ForEach-Object {
    if (-not (Test-Path $_)) { $healthIssues += "$(Split-Path $_ -Leaf) missing" }
}

# 0d. Ensure directories exist
@("$baseDir\.claude\hook_perf","$baseDir\.claude\session_history","$baseDir\projects\C--Users-z1439--claude\memory") | ForEach-Object {
    if (-not (Test-Path $_)) { try { New-Item -ItemType Directory -Force $_ | Out-Null } catch { $healthIssues += "cannot create $_" } }
}

# 0e. Auto-heal from recovery suggestions
$recFile = "$baseDir\.claude\recovery_suggestions.json"
if (Test-Path $recFile) {
    try {
        $recs = Get-Content $recFile -Raw | ConvertFrom-Json
        if ($recs.Count -gt 0) { $healthIssues += "Prior session had $($recs.Count) tool failure patterns — review recovery_suggestions.json" }
        Remove-Item $recFile -Force -ErrorAction SilentlyContinue
    } catch {}
}

if ($healthIssues.Count -gt 0) {
    Write-Output "HEALTH: $($healthIssues -join ' | ')"
}

# ═══════════════════════════════════════════
# PHASE 1: Verify all .ps1 scripts parse clean
# ═══════════════════════════════════════════
$scriptsDir = "$env:USERPROFILE\.claude\scripts"
$errors = @()
$nullVar = $null
$parseErrors = @()

Get-ChildItem $scriptsDir -Recurse -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $nullVar = $null
        $parseErrors = @()
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$nullVar, [ref]$parseErrors)
        if ($parseErrors.Count -gt 0) {
            $errors += "$($_.Name): $($parseErrors.Count) parse error(s)"
        }
    } catch {
        $errors += "$($_.Name): $_"
    }
}
$totalScripts = (Get-ChildItem $scriptsDir -Recurse -Filter "*.ps1" -ErrorAction SilentlyContinue).Count

# ═══════════════════════════════════════════
# PHASE 2: Ebbinghaus memory scoring
# ═══════════════════════════════════════════
$memoryDir = "$env:USERPROFILE\.claude\projects\C--Users-z1439--claude\memory"
$memIndex = Join-Path $memoryDir "MEMORY.md"
$stateFile = "$env:USERPROFILE\.claude\.claude\memory_scores.json"

if (Test-Path $memIndex) {
    $state = @{}
    if (Test-Path $stateFile) {
        try {
            $raw = Get-Content $stateFile -Raw -Encoding UTF8 -ErrorAction Stop
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

    if ($entries.Count -gt 0) {
        $now = Get-Date
        foreach ($entry in $entries) {
            $created = $null
            $memFile = Join-Path $memoryDir $entry.path
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

        $state | ConvertTo-Json -Depth 5 | Set-Content $stateFile -Encoding UTF8

        # Rewrite MEMORY.md with updated scores
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
    }
}

# ═══════════════════════════════════════════
# PHASE 3: Inject CLAUDE.local.md context
# ═══════════════════════════════════════════
$localMd = "$env:USERPROFILE\.claude\CLAUDE.local.md"
$ctxLines = @()

if (Test-Path $localMd) {
    $content = Get-Content $localMd -Raw -Encoding UTF8
    $currentTask = ''; $recentFindings = ''; $successPatterns = ''
    if ($content -match '(?s)## 当前任务\n(.*?)(?=\n##|\z)') { $currentTask = $Matches[1].Trim() }
    if ($content -match '(?s)## 最近发现\n(.*?)(?=\n##|\z)') { $recentFindings = $Matches[1].Trim() }
    if ($content -match '(?s)## 成功模式\n(.*?)(?=\n##|\z)') { $successPatterns = $Matches[1].Trim() }
    if ($currentTask) { $ctxLines += "当前: $currentTask" }
    if ($recentFindings) { $ctxLines += "最近: $recentFindings" }
    if ($successPatterns) { $ctxLines += "成功: $successPatterns" }
}

# ═══════════════════════════════════════════
# OUTPUT: summary + context injection JSON
# ═══════════════════════════════════════════
$statusMsg = if ($errors.Count -gt 0) {
    "SYNTAX ERRORS: $($errors -join '; ')"
} else {
    "All scripts OK ($totalScripts checked)"
}

if ($ctxLines.Count -gt 0) {
    Write-Output "$statusMsg`n$(@{ hookSpecificOutput = @{ hookEventName = "SessionStart"; additionalContext = ($ctxLines -join "`n") } } | ConvertTo-Json -Compress)"
} else {
    Write-Output $statusMsg
}

# Perf log
$perfDir = "$env:USERPROFILE\.claude\.claude\hook_perf"
if (-not (Test-Path $perfDir)) { New-Item -ItemType Directory -Force $perfDir | Out-Null }
@{ t = (Get-Date -Format "o"); h = "session-start"; d = $sw.ElapsedMilliseconds; e = $totalScripts } |
    ConvertTo-Json -Compress | Add-Content "$perfDir\session-start.jsonl" -Encoding UTF8

if ($errors.Count -gt 0) { exit 1 } else { exit 0 }
