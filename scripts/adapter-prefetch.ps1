# adapter-prefetch.ps1 — Context prefetch: what will Claude need this cycle?
# Pre-computes and caches context that would otherwise require multiple tool calls.
# Usage:
#   adapter-prefetch.ps1              → full prefetch, outputs JSON for injection
#   adapter-prefetch.ps1 -Keys <k1,k2> → only prefetch specific keys
#   adapter-prefetch.ps1 -Summary      → human-readable summary
#   adapter-prefetch.ps1 -Cache        → write to cache file for next cycle
param([string]$Keys, [switch]$Summary, [switch]$Cache, [switch]$Raw)

$ErrorActionPreference = "Continue"
$baseDir = "$env:USERPROFILE\.claude"
$cacheFile = "$baseDir\.claude\prefetch_cache.json"

$result = @{
    timestamp = (Get-Date -Format "o")
    health = $null
    pending = $null
    memory = $null
    evolution = $null
    rules = $null
}

# ── Health (fast, always) ──
if (-not $Keys -or $Keys -match "health") {
    try {
        $healthOut = python "$baseDir\scripts\health-check.py" 2>$null
        $result.health = $healthOut -join " | "
    } catch { $result.health = "unavailable" }
}

# ── Pending tasks ──
if (-not $Keys -or $Keys -match "pending") {
    $pending = @{}
    $haltFile = "$baseDir\.claude\HALT"
    if (Test-Path $haltFile) { $pending.halted = $true }

    $loopState = "$baseDir\.claude\loop_state.json"
    if (Test-Path $loopState) {
        try {
            $ls = Get-Content $loopState -Raw | ConvertFrom-Json
            $pending.loop_iteration = $ls.iteration
            $pending.loop_streak = $ls.streak
        } catch {}
    }

    $handoff = "$baseDir\handoff.md"
    if (Test-Path $handoff) {
        $pending.handoff = (Get-Content $handoff -Raw -Encoding UTF8).Substring(0, [math]::Min(500, (Get-Item $handoff).Length))
    }

    $activeTask = "$baseDir\.claude\active_task.md"
    if (Test-Path $activeTask) {
        $pending.active_task = (Get-Content $activeTask -Raw).Trim()
    }

    $result.pending = $pending
}

# ── Memory snapshot ──
if (-not $Keys -or $Keys -match "memory") {
    $memIndex = "$baseDir\projects\C--Users-z1439--claude\memory\MEMORY.md"
    if (Test-Path $memIndex) {
        $entries = @(Get-Content $memIndex -Encoding UTF8 | Where-Object { $_ -match '^\- \[' })
        $result.memory = @{
            total = $entries.Count
            fresh = ($entries | Where-Object { $_ -match 'fresh' }).Count
            aging = ($entries | Where-Object { $_ -match 'aging' }).Count
            sample = ($entries | Select-Object -First 5) -join "`n"
        }
    }
}

# ── Evolution status ──
if (-not $Keys -or $Keys -match "evolution") {
    $evoLog = "$baseDir\.claude\evolution_log.jsonl"
    if (Test-Path $evoLog) {
        $lastLine = Get-Content $evoLog -Tail 1 -ErrorAction SilentlyContinue
        if ($lastLine) {
            try { $lastEvo = $lastLine | ConvertFrom-Json; $result.evolution = $lastEvo } catch {}
        }
    }

    $evoGate = "$baseDir\.claude\evo_gate.json"
    if (Test-Path $evoGate) {
        try {
            $gate = Get-Content $evoGate -Raw | ConvertFrom-Json
            $result.evolution = @{} + $result.evolution + @{
                gated = (@($gate.recent_evo_timestamps | Where-Object { [datetime]$_ -gt (Get-Date).AddDays(-7) })).Count -ge 10
            }
        } catch {}
    }
}

# ── Rule effectiveness ──
if (-not $Keys -or $Keys -match "rules") {
    $rulesDir = "$baseDir\.claude\rules"
    if (Test-Path $rulesDir) {
        $ruleFiles = @(Get-ChildItem $rulesDir -Filter "*.md").Count
        $result.rules = @{ files = $ruleFiles }
    }
}

# ── Output ──
if ($Cache) {
    $result.cached_at = (Get-Date -Format "o")
    $result | ConvertTo-Json -Depth 4 | Set-Content $cacheFile -Encoding UTF8
    Write-Output "Cached to $cacheFile"
    exit 0
}

if ($Summary) {
    Write-Output @"
╔══════════════════════════════════════╗
║  PREFETCH SUMMARY                   ║
╠══════════════════════════════════════╣
║ Health:  $($result.health)
║ Loop:    #$($result.pending.loop_iteration) streak=$($result.pending.loop_streak)
║ Memory:  $($result.memory.total) entries ($($result.memory.fresh) fresh)
║ Evo:     $($result.evolution.timestamp)
║ Rules:   $($result.rules.files) files
╚══════════════════════════════════════╝
"@
    exit 0
}

# Default: JSON output
$result | ConvertTo-Json -Depth 4
