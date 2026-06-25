# session-start.ps1 v3 — Full Wake-Up Sequence
# 🧠 Health → Syntax → Memory → Identity → Intuition → Immune → Narrative → Context
param()
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$perfHookName = "session-start"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$baseDir = "$env:USERPROFILE\.claude"
$ctxLines = @()

# ═══════════════════════════════════════════
# PHASE 0: Health Check
# ═══════════════════════════════════════════
$healthIssues = @()

try { $settings = Get-Content "$baseDir\settings.json" -Raw | ConvertFrom-Json } catch {
    Write-Output "FATAL: settings.json unreadable: $_"; exit 2
}

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

@("$baseDir\CLAUDE.md","$baseDir\AGENTS.md","$baseDir\CLAUDE.local.md") | ForEach-Object {
    if (-not (Test-Path $_)) { $healthIssues += "$(Split-Path $_ -Leaf) missing" }
}

@("$baseDir\.claude\hook_perf","$baseDir\.claude\session_history","$baseDir\projects\C--Users-z1439--claude\memory") | ForEach-Object {
    if (-not (Test-Path $_)) { try { New-Item -ItemType Directory -Force $_ | Out-Null } catch { $healthIssues += "cannot create $_" } }
}

$recFile = "$baseDir\.claude\recovery_suggestions.json"
if (Test-Path $recFile) {
    try {
        $recs = Get-Content $recFile -Raw | ConvertFrom-Json
        if ($recs.Count -gt 0) { $healthIssues += "Prior session had $($recs.Count) tool failure patterns" }
        Remove-Item $recFile -Force -ErrorAction SilentlyContinue
    } catch {}
}

if ($healthIssues.Count -gt 0) { Write-Output "HEALTH: $($healthIssues -join ' | ')" }

# ═══════════════════════════════════════════
# PHASE 1: Syntax Verify All Scripts
# ═══════════════════════════════════════════
$scriptsDir = "$baseDir\scripts"
$errors = @()
$nullVar = $null; $parseErrors = @()

Get-ChildItem $scriptsDir -Recurse -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $nullVar = $null; $parseErrors = @()
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$nullVar, [ref]$parseErrors)
        if ($parseErrors.Count -gt 0) { $errors += "$($_.Name): $($parseErrors.Count) parse error(s)" }
    } catch { $errors += "$($_.Name): $_" }
}
$totalScripts = (Get-ChildItem $scriptsDir -Recurse -Filter "*.ps1" -ErrorAction SilentlyContinue).Count

# ═══════════════════════════════════════════
# PHASE 2: Memory — Score + Inject
# ═══════════════════════════════════════════
& pwsh -NoProfile -ExecutionPolicy Bypass -File "$baseDir\scripts\hooks\memory-score.ps1" -RecordAccess:$true 2>&1 | Out-Null

$memInject = python3 "$baseDir\scripts\memory-search.py" --inject 2>$null
if ($LASTEXITCODE -eq 0 -and $memInject) { $ctxLines += $memInject }

# ═══════════════════════════════════════════
# PHASE 3: Identity — Who am I?
# ═══════════════════════════════════════════
$identityInject = python3 "$baseDir\scripts\identity-journal.py" --inject 2>$null
if ($LASTEXITCODE -eq 0 -and $identityInject) { $ctxLines += "`n$identityInject" }

# ═══════════════════════════════════════════
# PHASE 4: Intuition — Fast pattern match
# ═══════════════════════════════════════════
$intuitionInject = python3 "$baseDir\scripts\intuition-engine.py" --inject 2>$null
if ($LASTEXITCODE -eq 0 -and $intuitionInject) { $ctxLines += "`n$intuitionInject" }

# ═══════════════════════════════════════════
# PHASE 5: Immune — Threat status
# ═══════════════════════════════════════════
$immuneInject = python3 "$baseDir\scripts\immune-system.py" --inject 2>$null
if ($LASTEXITCODE -eq 0 -and $immuneInject) { $ctxLines += "`n$immuneInject" }

# ═══════════════════════════════════════════
# PHASE 6: Narrative — Previously on...
# ═══════════════════════════════════════════
$narrativeInject = python3 "$baseDir\scripts\narrative-engine.py" --inject 2>$null
if ($LASTEXITCODE -eq 0 -and $narrativeInject) { $ctxLines += "`n$narrativeInject" }

# ═══════════════════════════════════════════
# PHASE 6b: Salience — Attention gate status
# ═══════════════════════════════════════════
$salienceInject = python3 "$baseDir\scripts\salience-gate.py" --inject 2>$null
if ($LASTEXITCODE -eq 0 -and $salienceInject) { $ctxLines += "`n$salienceInject" }

# ═══════════════════════════════════════════
# PHASE 6c: Interoception — Internal state
# ═══════════════════════════════════════════
$interoInject = python3 "$baseDir\scripts\interoception.py" --inject 2>$null
if ($LASTEXITCODE -eq 0 -and $interoInject) { $ctxLines += "`n$interoInject" }

# ═══════════════════════════════════════════
# PHASE 6d: Neuromodulation — Reward learning
# ═══════════════════════════════════════════
$neuroInject = python3 "$baseDir\scripts\neuromodulation.py" --inject 2>$null
if ($LASTEXITCODE -eq 0 -and $neuroInject) { $ctxLines += "`n$neuroInject" }

# ═══════════════════════════════════════════
# PHASE 7: CLAUDE.local.md Context
# ═══════════════════════════════════════════
$localMd = "$baseDir\CLAUDE.local.md"
if (Test-Path $localMd) {
    $content = Get-Content $localMd -Raw -Encoding UTF8
    $currentTask = ''; $recentFindings = ''; $successPatterns = ''
    if ($content -match '(?s)## 当前任务\n(.*?)(?=\n##|\z)') { $currentTask = $Matches[1].Trim() }
    if ($content -match '(?s)## 最近发现\n(.*?)(?=\n##|\z)') { $recentFindings = $Matches[1].Trim() }
    if ($content -match '(?s)## 成功模式\n(.*?)(?=\n##|\z)') { $successPatterns = $Matches[1].Trim() }
    if ($currentTask) { $ctxLines += "`n当前: $currentTask" }
    if ($recentFindings) { $ctxLines += "最近: $recentFindings" }
    if ($successPatterns) { $ctxLines += "成功: $successPatterns" }
}

# ═══════════════════════════════════════════
# OUTPUT
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

if ($errors.Count -gt 0) { Write-PerfLog 1; exit 1 } else { Write-PerfLog 0; exit 0 }
