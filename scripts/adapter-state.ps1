# adapter-state.ps1 — Instant state snapshot for Claude
# One call → everything I need to know about current system state
# Usage: adapter-state.ps1 [-Json] [-Brief]
param([switch]$Json, [switch]$Brief)

$ErrorActionPreference = "Continue"
$baseDir = "$env:USERPROFILE\.claude"
. "$baseDir\scripts\lib\dblog.ps1"  # SQLite log adapter

# ═══ 1. Health ═══
$health = @{ ok = $true; issues = @() }

# Disk
$disk = Get-PSDrive -Name (Split-Path $baseDir -Qualifier).TrimEnd(':') -ErrorAction SilentlyContinue
if ($disk) {
    $freeGB = [math]::Round($disk.Free / 1GB, 1)
    $totalGB = [math]::Round(($disk.Free + $disk.Used) / 1GB, 1)
    if ($freeGB -lt 10) { $health.issues += "Low disk: ${freeGB}GB free"; $health.ok = $false }
} else { $health.issues += "Cannot check disk"; $health.ok = $false }

# Git
$gitDirty = (git -C $baseDir status --short 2>$null | Measure-Object).Count
$gitLast = (git -C $baseDir log --oneline -1 2>$null) -replace '"',''

# Settings
$settingsValid = $true
try { $null = Get-Content "$baseDir\settings.json" -Raw | ConvertFrom-Json } catch { $settingsValid = $false; $health.issues += "settings.json invalid JSON"; $health.ok = $false }

# Hooks
$hookCount = 0
if ($settingsValid) {
    $s = Get-Content "$baseDir\settings.json" -Raw | ConvertFrom-Json
    foreach ($ev in $s.hooks.PSObject.Properties.Name) {
        foreach ($g in $s.hooks.$ev) { $hookCount += $g.hooks.Count }
    }
}
$hookDir = "$baseDir\scripts\hooks"
$hookFiles = @(Get-ChildItem $hookDir -Filter "*.ps1" -ErrorAction SilentlyContinue).Count
$libFiles = @(Get-ChildItem "$baseDir\scripts\lib" -Filter "*.ps1" -ErrorAction SilentlyContinue).Count

# ═══ 2. Evolution ═══
$lastEvo = $null; $evo24h = 0
# Try SQLite first
$dbEvo = Read-DbLog -Source "evolution_log" -Tail 20
if ($dbEvo -and $dbEvo.items) {
    $lines = $dbEvo.items
    $lastEvo = $lines[0]
    $cutoff = (Get-Date).AddHours(-24).ToString("o")
    $evo24h = ($lines | Where-Object { $_.timestamp -gt $cutoff }).Count
} else {
    # Fallback to JSONL
    $evoLog = "$baseDir\.claude\evolution_log.jsonl"
    if (Test-Path $evoLog) {
        $lines = @(Get-Content $evoLog -Tail 20 -ErrorAction SilentlyContinue | Where-Object { $_ })
        if ($lines.Count -gt 0) {
            try { $lastEvo = ($lines[-1] | ConvertFrom-Json) } catch {}
        }
        $evo24h = ($lines | ForEach-Object {
            try { ([datetime]($_ | ConvertFrom-Json).timestamp) } catch { $null }
        } | Where-Object { $_ -and ($_ -gt (Get-Date).AddHours(-24)) }).Count
    }
}

$evoGate = "$baseDir\.claude\evo_gate.json"
$evoGated = $false
if (Test-Path $evoGate) {
    try {
        $gate = Get-Content $evoGate -Raw | ConvertFrom-Json
        $recentCount = @($gate.recent_evo_timestamps | Where-Object { [datetime]$_ -gt (Get-Date).AddDays(-7) }).Count
        if ($recentCount -ge 10) { $evoGated = $true }
    } catch {}
}

$loopState = "$baseDir\.claude\loop_state.json"
$loopIter = 0; $loopStreak = 0
if (Test-Path $loopState) {
    try { $ls = Get-Content $loopState -Raw | ConvertFrom-Json; $loopIter = $ls.iteration; $loopStreak = $ls.streak } catch {}
}

# ═══ 3. Memory ═══
$memDir = Get-ChildItem "$baseDir\projects" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "memory" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
$memFiles = @(Get-ChildItem $memDir -Recurse -Filter "*.md" -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne "MEMORY.md" }).Count
$memIndex = "$memDir\MEMORY.md"
$memIndexed = 0
if (Test-Path $memIndex) {
    $memIndexed = @(Get-Content $memIndex -Encoding UTF8 | Where-Object { $_ -match '^\- \[' }).Count
}
$memTree = "$memDir\tree.json"
$treeStale = $false
if (Test-Path $memTree) {
    try {
        $tree = Get-Content $memTree -Raw | ConvertFrom-Json
        $treeAge = ((Get-Date) - [datetime]$tree.updated).TotalHours
        if ($treeAge -gt 24) { $treeStale = $true }
    } catch {}
}

# ═══ 4. Friction & Failures ═══
$cutoff24h = (Get-Date).AddHours(-24).ToString("o")
$friction24h = 0
$dbFric = Read-DbLog -Source "friction/events" -Tail 200
if ($dbFric -and $dbFric.items) {
    $friction24h = ($dbFric.items | Where-Object { $_.timestamp -gt $cutoff24h }).Count
} else {
    $frictionDir = "$baseDir\.claude\tellonce-state\friction"
    if (Test-Path "$frictionDir\events.jsonl") {
        $friction24h = @(Get-Content "$frictionDir\events.jsonl" -ErrorAction SilentlyContinue | Where-Object {
            try { ([datetime]($_ | ConvertFrom-Json).timestamp) -gt (Get-Date).AddHours(-24) } catch { $false }
        }).Count
    }
}

$failures24h = 0
$dbFail = Read-DbLog -Source "tool_failures" -Tail 200
if ($dbFail -and $dbFail.items) {
    $failures24h = ($dbFail.items | Where-Object { $_.timestamp -gt $cutoff24h }).Count
} else {
    $failureDir = "$baseDir\.claude\tool_failures"
    if (Test-Path "$failureDir\failures.jsonl") {
        $failures24h = @(Get-Content "$failureDir\failures.jsonl" -ErrorAction SilentlyContinue | Where-Object {
            try { ([datetime]($_ | ConvertFrom-Json).timestamp) -gt (Get-Date).AddHours(-24) } catch { $false }
        }).Count
    }
}

# ═══ 5. Pending ═══
$haltFile = "$baseDir\.claude\HALT"
$halted = Test-Path $haltFile
$handoff = "$baseDir\handoff.md"
$hasHandoff = Test-Path $handoff
$activeTask = "$baseDir\.claude\active_task.md"
$hasActiveTask = Test-Path $activeTask

# ═══ 6. Performance ═══
$slowHooks = @()
# Try SQLite first — single query for all hook_perf
$dbPerf = Read-DbLog -Source "hook_perf" -Tail 250 -AsJson
if ($dbPerf) {
    $recentPerf = $dbPerf | Where-Object { $_.d -gt 2000 }
    $byHook = $recentPerf | Group-Object { $_.h }
    foreach ($h in $byHook) {
        $slowHooks += "$($h.Name): $($h.Group[0].d)ms"
    }
} else {
    # Fallback to JSONL directory scan
    $perfDir = "$baseDir\.claude\hook_perf"
    if (Test-Path $perfDir) {
        Get-ChildItem $perfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
            $last = Get-Content $_.FullName -Tail 5 -ErrorAction SilentlyContinue | Where-Object { $_ } | ForEach-Object {
                try { $_ | ConvertFrom-Json } catch { $null }
            } | Where-Object { $_.d -gt 2000 }
            if ($last) { $slowHooks += "$($_.BaseName): $($last.d)ms" }
        }
    }
}

# ═══ OUTPUT ═══
if ($Brief) {
    $emoji = if ($health.ok -and -not $halted -and -not $evoGated) { "✅" } else { "⚠️" }
    Write-Output "$emoji L$loopIter | Git:$gitDirty | Mem:${memFiles}f/${memIndexed}i | Evo:${evo24h}/24h | Fric:$friction24h | Fail:$failures24h"
    exit 0
}

if ($Json) {
    @{
        health = $health
        git = @{ dirty = $gitDirty; last_commit = $gitLast }
        hooks = @{ total = $hookCount; files = $hookFiles; lib = $libFiles }
        evolution = @{ last = $lastEvo; count_24h = $evo24h; gated = $evoGated }
        loop = @{ iteration = $loopIter; streak = $loopStreak }
        memory = @{ files = $memFiles; indexed = $memIndexed; tree_stale = $treeStale }
        friction_24h = $friction24h
        failures_24h = $failures24h
        flags = @{ halted = $halted; handoff = $hasHandoff; active_task = $hasActiveTask }
        slow_hooks = $slowHooks
    } | ConvertTo-Json -Depth 3
    exit 0
}

# Rich output
Write-Output @"

╔═══════════════════════════════════════════╗
║  SYSTEM STATE                     L$loopIter ║
╠═══════════════════════════════════════════╣
║ Health:   $($health.ok ? 'OK' : "ISSUES: $($health.issues -join ', ')")
║ Disk:     ${freeGB}GB / ${totalGB}GB
║ Git:      $gitDirty dirty, $gitLast
║ Hooks:    $hookCount hooks, $hookFiles scripts, $libFiles lib
╠═══════════════════════════════════════════╣
║ Evo:      ${evo24h}/24h, gated=$evoGated
║ Memory:   $memFiles files, $memIndexed indexed, tree_stale=$treeStale
║ Friction: $friction24h/24h
║ Failures: $failures24h/24h
╠═══════════════════════════════════════════╣
║ Halted:   $halted
║ Handoff:  $hasHandoff
║ Task:     $hasActiveTask
╚═══════════════════════════════════════════╝
$($slowHooks.Count -gt 0 ? "SLOW: $($slowHooks -join ', ')" : "")
"@
