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
# PHASE 2: Ebbinghaus memory scoring (delegated to shared module)
# ═══════════════════════════════════════════
& pwsh -NoProfile -ExecutionPolicy Bypass -File "$baseDir\scripts\hooks\memory-score.ps1" 2>&1 | Out-Null

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
