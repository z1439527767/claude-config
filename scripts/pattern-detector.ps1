# pattern-detector.ps1 — Passive rules → Active detection
# Detects: error repeats (→ rule creation), idle patterns (→ rust alert)
# Usage: pattern-detector.ps1 [-Quiet] [-Fix]
param([switch]$Quiet, [switch]$Fix)

$ErrorActionPreference = "Stop"
$HomeDir = $env:USERPROFILE
$issues = @()
$signals = @()

# ===== 1. ERROR REPEAT DETECTION =====
# Rule: 同错两次 → 写规则。Detect repeated error patterns in failures.jsonl
$failuresFile = "$HomeDir/.claude/.claude/tool_failures/failures.jsonl"
if (Test-Path $failuresFile) {
    $errors = @{}
    $recentErrors = @()
    $cutoff = (Get-Date).AddHours(-24)

    Get-Content $failuresFile | ForEach-Object {
        if (-not $_.Trim()) { return }
        try {
            $entry = $_ | ConvertFrom-Json
            $ts = [DateTime]::Parse($entry.timestamp)
            if ($ts -gt $cutoff) {
                # Extract error signature: first 80 chars, normalize specifics
                $sig = $entry.error -replace 'C:\\[^\s,;]+', '<PATH>' `
                    -replace '\/[a-z]+\/[a-z]+\/[^\s,;]+', '<PATH>' `
                    -replace '\d{4}-\d{2}-\d{2}T[\d:\.\-]+', '<TIMESTAMP>' `
                    -replace '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<UUID>'
                if ($sig.Length -gt 80) { $sig = $sig.Substring(0, 80) }
                if (-not $errors[$sig]) { $errors[$sig] = @() }
                $errors[$sig] += @{ ts = $ts; tool = $entry.tool_name }
            }
        } catch {}
    }

    $repeats = $errors.GetEnumerator() | Where-Object { $_.Value.Count -ge 2 }
    if ($repeats) {
        foreach ($r in $repeats) {
            $tools = ($r.Value | ForEach-Object { $_.tool } | Sort-Object -Unique) -join ', '
            $issues += "[error-repeat] $($r.Value.Count)x via $tools — sig: $($r.Key.Substring(0, [Math]::Min(60, $r.Key.Length)))"
        }
    }
}

# ===== 2. IDLE PATTERN DETECTION =====
# Rule: 自主找活，不停。Detect: no file changes in >1h (while session active)
$ralphState = "$HomeDir/.claude/.claude/ralph-state"
if (-not (Test-Path $ralphState)) { New-Item -ItemType Directory -Force $ralphState | Out-Null }

$idleFile = "$ralphState/activity_log.jsonl"
$lastActivity = $null
if (Test-Path $idleFile) {
    $lastLine = Get-Content $idleFile -Tail 1
    if ($lastLine) {
        try { $lastActivity = $lastLine | ConvertFrom-Json } catch {}
    }
}

# Record current activity (compute values outside hashtable to avoid inline try/catch)
$commitCount = 0; try { $commitCount = [int](git -C "$HomeDir/.claude" log --since="1 hour ago" --oneline 2>$null | Measure-Object).Count } catch {}
$changedCount = 0; try { $changedCount = [int]((git -C "$HomeDir/.claude" diff --name-only HEAD 2>$null) | Measure-Object).Count } catch {}

$currentActivity = @{
    timestamp = (Get-Date -Format "o")
    git_commits = $commitCount
    files_changed = $changedCount
    audit_done = (Test-Path "$HomeDir/.claude/.claude/audit_state.json")
}
$currentActivity | ConvertTo-Json -Compress | Add-Content $idleFile -Encoding UTF8

# Check for idle pattern
if ($lastActivity) {
    $elapsed = (Get-Date) - [DateTime]::Parse($lastActivity.timestamp)
    if ($elapsed.TotalHours -gt 1) {
        $prevChanges = [int]$lastActivity.files_changed
        $currChanges = $currentActivity.files_changed
        if ($prevChanges -eq 0 -and $currChanges -eq 0) {
            $issues += "[idle-pattern] No file changes in $([Math]::Round($elapsed.TotalHours,1))h — possible stall"
        }
    }
}

# ===== 3. WORK STACK TRACKING =====
# Track which priority level is being worked on
$workStackFile = "$ralphState/work_stack.json"
$stack = @{ p2_checks = 0; p3_reviews = 0; p4_sediment = 0; p5_optimize = 0; last_update = (Get-Date -Format "o") }
if (Test-Path $workStackFile) {
    try { $stack = Get-Content $workStackFile -Raw | ConvertFrom-Json } catch {}
}

# Infer current level from recent activity
$recentCommits = try { git -C "$HomeDir/.claude" log --since="2 hours ago" --oneline 2>$null } catch { "" }
if ($recentCommits -match 'fix:|auto:') { $stack.p2_checks++ }
elseif ($recentCommits -match 'review|audit') { $stack.p3_reviews++ }
elseif ($recentCommits -match 'feat:|refactor|rule|memory') { $stack.p4_sediment++ }
elseif ($recentCommits -match 'perf|clean|optimize') { $stack.p5_optimize++ }

$stack.last_update = (Get-Date -Format "o")
$tmpStack = "$workStackFile.tmp.$([Guid]::NewGuid().ToString("N").Substring(0,8))"
try { $stack | ConvertTo-Json | Set-Content $tmpStack -Encoding UTF8; Move-Item -Force $tmpStack $workStackFile } catch {}

# Check if stuck at P2 (only checks, no real work) for >2 rounds
$p2Only = ($stack.p2_checks -gt 3) -and ($stack.p3_reviews -eq 0) -and ($stack.p4_sediment -eq 0) -and ($stack.p5_optimize -eq 0)
if ($p2Only) {
    $issues += "[workstack-stuck] P2-heavy ($($stack.p2_checks) checks, 0 P3-P5 work) — need to escalate to real tasks"
}

# ===== 4. KG SIGNAL CLEANUP =====
# Trim kg_signals.jsonl if >200 lines (keep last 50)
$signalFile = "$HomeDir/.claude/.claude/kg_signals.jsonl"
if ((Test-Path $signalFile) -and $Fix) {
    $lineCount = (Get-Content $signalFile | Measure-Object).Count
    if ($lineCount -gt 200) {
        $keep = Get-Content $signalFile -Tail 50
        $tmpSig = "$signalFile.tmp.$([Guid]::NewGuid().ToString("N").Substring(0,8))"
        try { $keep | Set-Content $tmpSig -Encoding UTF8; Move-Item -Force $tmpSig $signalFile } catch {}
    }
}

# ===== OUTPUT =====
if ($issues.Count -gt 0) {
    if (-not $Quiet) {
        Write-Output "[pattern-detector] SIGNALS: $($issues.Count)"
        foreach ($i in $issues) { Write-Output "  ! $i" }
    }

    # Emit KG signals for detected patterns
    . "$HomeDir/.claude/scripts/lib/kg-signal.ps1"
    foreach ($i in $issues) {
        if ($i -match 'error-repeat') {
            Write-KgSignal -Source "pattern-detector" -EntityName "pattern-$((Get-Date).ToString('yyyyMMdd-HHmm'))" -EntityType "detected-pattern" -Observations @($i, "Rule trigger: 同错两次 → 写规则。LLM should check failures.jsonl and create a prevention rule") -Priority "high"
        } elseif ($i -match 'idle-pattern') {
            Write-KgSignal -Source "pattern-detector" -EntityName "idle-$((Get-Date).ToString('yyyyMMdd-HHmm'))" -EntityType "stall-warning" -Observations @($i, "Rule trigger: 自主找活不停。LLM should review work stack and find next task") -Priority "high"
        } elseif ($i -match 'workstack-stuck') {
            Write-KgSignal -Source "pattern-detector" -EntityName "stuck-$((Get-Date).ToString('yyyyMMdd-HHmm'))" -EntityType "stall-warning" -Observations @($i, "Rule trigger: 降级规则 — 连续P2无新发现 → 降到P3/P4/P5。LLM should do P3-P5 real work") -Priority "high"
        }
    }
    exit 1
} else {
    if (-not $Quiet) { Write-Output "[pattern-detector] OK: no patterns detected" }
    exit 0
}
