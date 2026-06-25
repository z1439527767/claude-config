# health-check.ps1 — SessionStart: validate all hook dependencies before session begins
param()
$ErrorActionPreference = "Continue"
$issues = @()

$base = "$env:USERPROFILE\.claude"
$settingsJson = Join-Path $base "settings.json"
$scriptsDir = Join-Path $base "scripts\hooks"

# 1. Settings.json readable + valid JSON
try {
    $settings = Get-Content $settingsJson -Raw | ConvertFrom-Json
} catch {
    $issues += "FATAL: settings.json invalid or unreadable: $_"
    Write-Output ($issues -join "`n")
    exit 2
}

# 2. Every hook command references an existing script
$missingScripts = @()
foreach ($eventName in $settings.hooks.PSObject.Properties.Name) {
    foreach ($group in $settings.hooks.$eventName) {
        foreach ($h in $group.hooks) {
            if ($h.command -match '([^\\"]+\.ps1)') {
                $scriptName = $Matches[1]
                $scriptPath = Join-Path $scriptsDir $scriptName
                if (-not (Test-Path $scriptPath)) {
                    $missingScripts += "$eventName → $scriptName"
                }
            }
        }
    }
}
if ($missingScripts.Count -gt 0) {
    $issues += "MISSING SCRIPTS: $($missingScripts -join ', ')"
}

# 3. Every script in hooks/ parses clean
$parseErrors = @()
Get-ChildItem $scriptsDir -File -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    $nullVar = $null; $pe = @()
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$nullVar, [ref]$pe)
    if ($pe.Count -gt 0) {
        $parseErrors += "$($_.Name): $($pe.Count) error(s)"
    }
}
if ($parseErrors.Count -gt 0) {
    $issues += "SYNTAX ERRORS: $($parseErrors -join '; ')"
}

# 4. Key config files exist
$keyFiles = @(
    (Join-Path $base "CLAUDE.md"),
    (Join-Path $base "AGENTS.md"),
    (Join-Path $base "CLAUDE.local.md"),
    $settingsJson
)
$missing = @()
foreach ($f in $keyFiles) {
    if (-not (Test-Path $f)) { $missing += Split-Path $f -Leaf }
}
if ($missing.Count -gt 0) {
    $issues += "MISSING FILES: $($missing -join ', ')"
}

# 5. Relevant directories exist
$dirs = @(
    "$base\.claude",
    "$base\.claude\hook_perf",
    "$base\projects\C--Users-z1439--claude\memory"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        try { New-Item -ItemType Directory -Force $d | Out-Null } catch {
            $issues += "CANNOT CREATE: $d"
        }
    }
}

# 6. Auto-heal: apply recovery suggestions from previous sessions
$recFile = "$base\.claude\recovery_suggestions.json"
if (Test-Path $recFile) {
    try {
        $recs = Get-Content $recFile -Raw | ConvertFrom-Json
        $healed = @()
        foreach ($rec in $recs) {
            if ($rec.failures -ge 3) {
                # If Write tool fails frequently, ensure temp directory exists
                if ($rec.tool -eq "Write") {
                    $tmpDir = "$base\.claude\tmp"
                    if (-not (Test-Path $tmpDir)) { New-Item -ItemType Directory -Force $tmpDir | Out-Null; $healed += "created tmp dir" }
                }
                # If Edit tool fails, run syntax check on all scripts to detect corruption
                if ($rec.tool -eq "Edit") {
                    $issues += "Edit tool has $($rec.failures) recent failures — verify file integrity before editing"
                }
            }
        }
        if ($healed.Count -gt 0) { Write-Output "AUTO-HEAL: $($healed -join ', ')" }
        Remove-Item $recFile -Force -ErrorAction SilentlyContinue
    } catch { }
}

# 7. Report
if ($issues.Count -gt 0) {
    Write-Output "HEALTH CHECK FAIL:`n$($issues -join "`n")"
    exit 1
}

$scriptCount = (Get-ChildItem $scriptsDir -File -Filter "*.ps1").Count
$hookCount = 0
$settings.hooks.PSObject.Properties | ForEach-Object { $hookCount += $_.Value.hooks.Count }
Write-Output "HEALTH: $hookCount hooks, $scriptCount scripts, all clear"
exit 0
