# proactive-opt.ps1 — SessionStart: identify optimization opportunities without friction signals
# Scans: script sizes, duplication, complexity, stale config
param()
$ErrorActionPreference = "Continue"
$perfHookName = "proactive-opt"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$base = "$env:USERPROFILE\.claude"
$scriptsDir = "$base\scripts\hooks"
$suggestions = @()

# ── 1. Large script detection (>300 lines → suggest splitting) ──
Get-ChildItem $scriptsDir -File -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    $lines = (Get-Content $_.FullName | Measure-Object -Line).Lines
    if ($lines -gt 300) {
        $suggestions += "$($_.Name): $lines lines — consider splitting into focused modules"
    }
}

# ── 2. Script last modified >90 days → may be stale ──
Get-ChildItem $scriptsDir -File -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    $age = ((Get-Date) - $_.LastWriteTime).TotalDays
    if ($age -gt 90) {
        $suggestions += "$($_.Name): untouched for $([int]$age)d — verify still needed"
    }
}

# ── 3. Duplicate code detection (same function name in multiple scripts) ──
$funcNames = @{}
Get-ChildItem $scriptsDir -File -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    $content = Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue
    if ($content -match 'function\s+(\w+)') {
        $fn = $Matches[1]
        if (-not $funcNames[$fn]) { $funcNames[$fn] = @() }
        $funcNames[$fn] += $_.Name
    }
}
foreach ($fn in $funcNames.Keys) {
    if ($funcNames[$fn].Count -gt 1) {
        $suggestions += "function '$fn' defined in $($funcNames[$fn].Count) scripts: $($funcNames[$fn] -join ', ') — consider shared module"
    }
}

# ── 4. Hook timeout inefficiency: timeout >10x actual avg → wasteful ──
$perfDir = "$base\.claude\hook_perf"
$settingsJson = "$base\settings.json"
if (Test-Path $perfDir) {
    try { $settings = Get-Content $settingsJson -Raw | ConvertFrom-Json } catch { $settings = $null }
    if ($settings) {
        Get-ChildItem $perfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
            $hookN = $_.BaseName
            $lines = Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue | Where-Object { $_ }
            $entries = @($lines | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ })
            if ($entries.Count -lt 10) { return }
            $durations = @($entries | ForEach-Object {
                if ($_.duration_ms) { [int]$_.duration_ms } elseif ($_.d) { [int]$_.d } else { 0 }
            } | Where-Object { $_ -gt 0 })
            if ($durations.Count -lt 10) { return }
            $avgMs = ($durations | Measure-Object -Average).Average

            foreach ($eventName in $settings.hooks.PSObject.Properties.Name) {
                foreach ($group in $settings.hooks.$eventName) {
                    foreach ($h in $group.hooks) {
                        if ($h.command -match [regex]::Escape($hookN)) {
                            $timeoutMs = [int]$h.timeout * 1000
                            if ($avgMs -gt 0 -and $timeoutMs / $avgMs -gt 10) {
                                $suggestions += "$hookN timeout $($h.timeout)s vs avg ${avgMs:N0}ms — 10x+ waste"
                            }
                        }
                    }
                }
            }
        }
    }
}

# ── 5. Config file line counts > recommended ──
$claudeLines = if (Test-Path "$base\CLAUDE.md") { (Get-Content "$base\CLAUDE.md" | Measure-Object -Line).Lines } else { 0 }
$agentsLines = if (Test-Path "$base\AGENTS.md") { (Get-Content "$base\AGENTS.md" | Measure-Object -Line).Lines } else { 0 }
if ($claudeLines -gt 80) { $suggestions += "CLAUDE.md: $claudeLines lines — target <80 for optimal compliance" }
if ($agentsLines -gt 15) { $suggestions += "AGENTS.md: $agentsLines lines — keep principles concise" }

# ── Report ──
if ($suggestions.Count -gt 0) {
    $reportFile = "$base\.claude\optimization_suggestions.json"
    $suggestions | ConvertTo-Json | Set-Content $reportFile -Encoding UTF8
    $msg = ($suggestions | ForEach-Object { "  $_" }) -join "`n"
    Write-Output "PROACTIVE:`n$msg"
}

Write-PerfLog 0; exit 0
