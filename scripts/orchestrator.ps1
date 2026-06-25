# orchestrator.ps1 — Expert-level 24/7 autonomous execution engine
# Synthesizes patterns from Nightcrawler + Claude Swarm + Nonstop Agent
param(
    [int]$MaxEpisodes = 100,
    [int]$EpisodeMinutes = 30,
    [float]$BudgetPerEpisode = 2.00,
    [float]$TotalBudget = 20.00
)

$ErrorActionPreference = "Continue"
$base = "$env:USERPROFILE\.claude"
$stateDir = "$base\.claude\orchestrator"
$episodeDir = "$stateDir\episodes"
$checkpointDir = "$stateDir\checkpoints"
$lockFile = "$stateDir\LOCK"
$stopFile = "$stateDir\STOP"
$stateFile = "$stateDir\STATE.json"
$taskFile = "$stateDir\tasks.json"
$handoffFile = "$base\.claude\handoff.md"
$cycleLog = "$base\.claude\cycle_log.jsonl"

# ── Ensure directories ──
foreach ($d in @($stateDir, $episodeDir, $checkpointDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Force $d | Out-Null }
}

# ═══════════════════════════════════════
# PID LOCK: prevent double-run (Nightcrawler pattern)
# ═══════════════════════════════════════
if (Test-Path $lockFile) {
    $oldPid = Get-Content $lockFile -Raw
    try {
        $oldProc = Get-Process -Id ([int]$oldPid) -ErrorAction Stop
        if ($oldProc -and -not $oldProc.HasExited) {
            Write-Output "ORCHESTRATOR: already running (PID $oldPid)"
            exit 0
        }
    } catch {
        # Stale lock — process died
        Write-Output "ORCHESTRATOR: stale lock detected (PID $oldPid gone), recovering"
    }
}
$pid | Set-Content $lockFile -Force

# ── Cleanup lock on exit ──
Register-EngineEvent -SourceIdentifier OrchestratorExit -Action {
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
} | Out-Null

# ═══════════════════════════════════════
# STATE: load or initialize (Claude Swarm file-state pattern)
# ═══════════════════════════════════════
$state = @{
    episode = 0
    total_improvements = 0
    total_errors = 0
    budget_spent = 0.0
    quality_scores = @()
    started_at = (Get-Date -Format "o")
    status = "running"
}

if (Test-Path $stateFile) {
    try {
        $loaded = Get-Content $stateFile -Raw | ConvertFrom-Json
        $state.episode = [int]$loaded.episode
        $state.total_improvements = [int]$loaded.total_improvements
        $state.total_errors = [int]$loaded.total_errors
        $state.budget_spent = [float]$loaded.budget_spent
        $state.quality_scores = @($loaded.quality_scores)
        $state.status = $loaded.status
    } catch { Write-Output "ORCHESTRATOR: corrupt state, reinitializing" }
}

# ═══════════════════════════════════════
# TASKS: immutable tracker (Nightcrawler pattern)
# ═══════════════════════════════════════
$tasks = @{}
if (Test-Path $taskFile) {
    try { $tasks = Get-Content $taskFile -Raw | ConvertFrom-Json } catch {}
}
if ($tasks.Count -eq 0) {
    $tasks = @{
        "syntax-health"    = @{ passes = $false; description = "All scripts parse clean, zero errors" }
        "hook-integrity"   = @{ passes = $false; description = "All hook refs point to existing scripts" }
        "rule-effectiveness" = @{ passes = $false; description = "No ineffective rules older than 14 days" }
        "timeout-optimal"  = @{ passes = $false; description = "All hook timeouts within 30% of actual avg" }
        "memory-clean"     = @{ passes = $false; description = "Zero expired memories, <3 stale" }
        "zero-orphans"     = @{ passes = $false; description = "No orphan scripts in hooks directory" }
        "quality-trend"    = @{ passes = $false; description = "Quality score stable or improving" }
        "context-budget"   = @{ passes = $false; description = "Total config lines < 200" }
    }
}

Write-Output "=== ORCHESTRATOR START ==="
Write-Output "Episode: $($state.episode + 1) | Budget: `$${BudgetPerEpisode}/ep | Max: $MaxEpisodes"
Write-Output "Tasks: $(($tasks.Values | Where-Object { -not $_.passes }).Count) pending"

# ═══════════════════════════════════════
# MAIN EPISODE LOOP
# ═══════════════════════════════════════
while ($state.episode -lt $MaxEpisodes) {
    $state.episode++
    $epStart = Get-Date
    $epNum = $state.episode
    Write-Output "`n=== EPISODE $epNum @ $(Get-Date -Format 'HH:mm:ss') ==="

    # ── CHECK: 8 termination conditions (Nightcrawler pattern) ──
    $shouldStop = $false
    $stopReason = ""

    if (Test-Path $stopFile) {
        $shouldStop = $true; $stopReason = "STOP file detected"
    }
    if ($state.total_errors -ge 10) {
        $shouldStop = $true; $stopReason = "Error threshold (10) reached"
    }
    if ($state.budget_spent -ge $TotalBudget) {
        $shouldStop = $true; $stopReason = "Total budget `$$TotalBudget exhausted"
    }
    if ($epNum -ge $MaxEpisodes) {
        $shouldStop = $true; $stopReason = "Max episodes ($MaxEpisodes) reached"
    }
    # Diminishing returns: last 3 episodes, no improvements
    if ($state.quality_scores.Count -ge 3) {
        $last3 = $state.quality_scores[-3..-1]
        $improved = ($last3[-1] -gt $last3[0])
        if (-not $improved -and $last3[-1] -ge ($last3 | Measure-Object -Maximum).Maximum) {
            $shouldStop = $true; $stopReason = "Diminishing returns (3 episodes no improvement)"
        }
    }
    # All tasks pass
    $pendingTasks = ($tasks.Values | Where-Object { -not $_.passes }).Count
    if ($pendingTasks -eq 0) {
        $shouldStop = $true; $stopReason = "All tasks complete"
    }

    if ($shouldStop) {
        Write-Output "TERMINATE: $stopReason"
        $state.status = "stopped"
        $state.stop_reason = $stopReason
        break
    }

    # ── RECONSTRUCT: read handoff ──
    $handoffContext = ""
    if (Test-Path $handoffFile) {
        $handoffContext = Get-Content $handoffFile -Raw -Encoding UTF8
    }

    # ── CHECKPOINT: snapshot before episode (Claude Swarm pattern) ──
    $checkpoint = @{
        episode = $epNum
        timestamp = (Get-Date -Format "o")
        state = $state | ConvertTo-Json -Compress
        tasks = $tasks | ConvertTo-Json -Compress
    }
    $checkpointFile = Join-Path $checkpointDir "episode_${epNum}.json"
    $checkpoint | ConvertTo-Json | Set-Content $checkpointFile -Encoding UTF8

    # ── EXECUTE: fresh claude -p per episode (Nightcrawler pattern) ──
    $prompt = @"
PREVIOUS HANDOFF:
$handoffContext

CURRENT TASKS (immutable, only flip false→true):
$($tasks | ConvertTo-Json)

STATE:
$($state | ConvertTo-Json)

YOUR MISSION:
1. Run health check: verify all scripts syntax, hook integrity, settings.json validity
2. Run evolution: L1 frictions→rules, L2 success→principles, L3 timeout tuning, L4 memory health, L5 proactive optimization
3. Run auto-distill: 3+ same-topic memories → principles
4. For EACH task above that now passes, flip it to true in the tasks output
5. Fix any issues found. Verify every change.
6. Write structured HANDOFF.md with: what changed, what improved, what needs next attention
7. Output final STATE as JSON with keys: improvements_this_episode, quality_score, errors_this_episode, budget_used_estimate
8. NEVER modify anything outside C:\Users\z1439\.claude\
"@

    Write-Output "  EXECUTING: claude -p (turns: 40, budget: `$$BudgetPerEpisode)"
    $result = & claude -p $prompt --max-turns 40 --max-budget-usd $BudgetPerEpisode --output-format json --model sonnet 2>&1
    $exitCode = $LASTEXITCODE

    # ── PARSE result ──
    $improvements = 0; $qualityScore = $state.quality_scores[-1]; $errors = 0; $cost = 0
    try {
        $parsed = $result | ConvertFrom-Json
        $cost = [float]$parsed.cost_usd
        $state.budget_spent += $cost
        # Try to extract structured data from result text
        $resultText = $parsed.result ?? ""
        if ($resultText -match 'quality_score["\s:]+(\d+)') { $qualityScore = [int]$Matches[1] }
        if ($resultText -match 'improvements_this_episode["\s:]+(\d+)') { $improvements = [int]$Matches[1] }
        if ($resultText -match 'errors_this_episode["\s:]+(\d+)') { $errors = [int]$Matches[1] }
    } catch {
        $errors++
        $state.total_errors++
        Write-Output "  PARSE FAILED: $($result.Substring(0, [Math]::Min(200, $result.Length)))"
    }

    $state.total_improvements += $improvements
    $state.total_errors += $errors
    $state.quality_scores += $qualityScore

    # ── UPDATE tasks (read fresh from handoff) ──
    if (Test-Path $handoffFile) {
        $newHandoff = Get-Content $handoffFile -Raw -Encoding UTF8
        foreach ($taskName in $tasks.Keys) {
            if (-not $tasks[$taskName].passes -and $newHandoff -match "$taskName.*?(complete|pass|done|fixed|clean)") {
                $tasks[$taskName].passes = $true
                Write-Output "  TASK COMPLETE: $taskName"
            }
        }
    }

    # ── SAVE state ──
    $state | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8
    $tasks | ConvertTo-Json | Set-Content $taskFile -Encoding UTF8

    # ── LOG episode ──
    $duration = [int]((Get-Date) - $epStart).TotalSeconds
    @{
        timestamp = (Get-Date -Format "o")
        episode = $epNum
        duration_s = $duration
        exit_code = $exitCode
        improvements = $improvements
        quality_score = $qualityScore
        errors = $errors
        cost = $cost
    } | ConvertTo-Json -Compress | Add-Content $cycleLog -Encoding UTF8

    # ── Maintain checkpoints (keep last 20) ──
    Get-ChildItem $checkpointDir -File -Filter "episode_*.json" |
        Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 |
        Remove-Item -Force -ErrorAction SilentlyContinue

    Write-Output "  DONE: ${duration}s | Score: $qualityScore | Cost: `$$cost | Impr: $improvements"

    # ── COOLDOWN: 10s between episodes (Nightcrawler pattern) ──
    Start-Sleep -Seconds 10
}

# ═══════════════════════════════════════
# COMPLETION REPORT
# ═══════════════════════════════════════
$report = @"
# ORCHESTRATOR COMPLETION REPORT
- Completed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
- Episodes: $($state.episode)
- Total improvements: $($state.total_improvements)
- Total errors: $($state.total_errors)
- Budget spent: `$$([math]::Round($state.budget_spent, 2))
- Quality scores: $($state.quality_scores -join ' → ')
- Stop reason: $($state.stop_reason ?? 'normal completion')
- Tasks status:
$($tasks.Keys | ForEach-Object { "  - $_: $($tasks[$_].passes ? 'PASS' : 'FAIL')" } | Out-String)
"@
$report | Set-Content "$stateDir\COMPLETION_REPORT.md" -Encoding UTF8
Write-Output "`n$report"

Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
Write-Output "ORCHESTRATOR END"
