# auto-distill.ps1 — SessionStart: detect distillation candidates, signal LLM to synthesize
# Architecture: hook DETECTS (deterministic threshold check), LLM SYNTHESIZES (actual content analysis)
# This is honest — we don't pretend PowerShell can derive principles from content.
param()
$ErrorActionPreference = "Continue"
$perfHookName = "auto-distill"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$memDir = Get-ChildItem "$env:USERPROFILE\.claude\projects" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "memory" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
if (-not $memDir) { $memDir = "$env:USERPROFILE\.claude\projects\C--Users-$env:USERNAME--claude\memory" }
$memIndex = Join-Path $memDir "MEMORY.md"
$distillState = "$env:USERPROFILE\.claude\.claude\distill_state.json"

if (-not (Test-Path $memIndex)) { Write-PerfLog 0; exit 0 }

# Parse MEMORY.md entries
$lines = (Get-Content $memIndex -Raw -Encoding UTF8) -split "`n"
$entries = @()
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^- \[(\S+)\]\(([^)]+)\) — (.+?)\s\[.+?\]$') {
        $entries += @{
            id          = $Matches[1]
            path        = $Matches[2]
            description = $Matches[3]
            fullPath    = Join-Path $memDir $Matches[2]
        }
    }
}

if ($entries.Count -lt 3) { Write-PerfLog 0; exit 0 }

# Load state — track which groups we've already signaled
$state = @{ signaled = @{}; last_counts = @{} }
if (Test-Path $distillState) {
    try { $existing = Get-Content $distillState -Raw | ConvertFrom-Json
        foreach ($prop in $existing.PSObject.Properties) {
            $state[$prop.Name] = @{}
            foreach ($k in $prop.Value.PSObject.Properties) {
                $state[$prop.Name][$k.Name] = $prop.Value.($k.Name)
            }
        }
    } catch { }
}

# Categorize entries by keyword similarity (deterministic grouping)
$groups = @{}
foreach ($e in $entries) {
    $desc = $e.description.ToLower()
    $category = "other"
    if ($desc -match '\b(?:hook|pretooluse|posttooluse|sessionstart|stop|event)\b') { $category = 'hooks' }
    elseif ($desc -match '\b(?:memor|记忆|遗忘|蒸馏|decay|score)\b') { $category = 'memory' }
    elseif ($desc -match '\b(?:error|bug|bug|fail|crash|broken|故障)\b') { $category = 'bugs' }
    elseif ($desc -match '\b(?:clean|清理|delete|删除|bloat|prune)\b') { $category = 'cleanup' }
    elseif ($desc -match '\b(?:rule|规则|principle|principle|behavior|行为|constraint)\b') { $category = 'rules' }
    elseif ($desc -match '\b(?:verif|验证|test|测试|review|审查)\b') { $category = 'verification' }
    elseif ($desc -match '\b(?:secur|安全|vuln|inject)\b') { $category = 'security' }
    if (-not $groups[$category]) { $groups[$category] = @() }
    $groups[$category] += $e
}

# Check each group for threshold — signal new candidates
$signals = @()
foreach ($cat in $groups.Keys) {
    $members = $groups[$cat]
    if ($members.Count -lt 3) { continue }

    $prevCount = if ($state.last_counts[$cat]) { [int]$state.last_counts[$cat] } else { 0 }
    $alreadySignaled = if ($state.signaled[$cat]) { [bool]$state.signaled[$cat] } else { $false }

    # Signal if: threshold met AND (new entries added OR never signaled before)
    if ($members.Count -gt $prevCount -and -not $alreadySignaled) {
        $signals += "[$cat] $($members.Count) entries (was $prevCount) — new candidates for distillation"
        $state.signaled[$cat] = $true
    } elseif ($members.Count -ge ($prevCount + 3) -and $alreadySignaled) {
        # Re-signal if 3+ NEW entries accumulated since last distillation
        $signals += "[$cat] $($members.Count) entries (+$($members.Count - $prevCount) new) — re-distillation recommended"
        $state.signaled[$cat] = $false  # reset to allow re-signal after actual distillation
    }
    $state.last_counts[$cat] = $members.Count
}

# Save state
$state | ConvertTo-Json -Depth 3 | Set-Content $distillState -Encoding UTF8

if ($signals.Count -gt 0) {
    Write-Output "DISTILL_SIGNAL: $($signals -join ' | ')"
}

Write-PerfLog 0; exit 0
