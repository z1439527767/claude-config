# self-audit.ps1 — 每轮结束后的自审计落盘
# 解决线性注意力问题：被动规则文本 → 主动文件检查
# 用法: self-audit.ps1 -Submit -Passed Q1,Q2,Q3,Q4,Q5 [-Failed Q3] [-Note "..."]
param(
    [switch]$Submit,
    [string]$Passed = "",
    [string]$Failed = "",
    [string]$Note = "",
    [switch]$Last,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
$auditFile = "$env:USERPROFILE\.claude\.claude\audit_log.jsonl"
$stateFile = "$env:USERPROFILE\.claude\.claude\audit_state.json"

# ── Status: check if audit is overdue ──
if ($Status) {
    $overdue = $true
    $lastTs = $null
    if (Test-Path $stateFile) {
        try {
            $state = Get-Content $stateFile -Raw | ConvertFrom-Json
            $lastTs = [DateTime]::Parse($state.last_audit)
            $elapsed = (Get-Date) - $lastTs
            if ($elapsed.TotalMinutes -lt 30) { $overdue = $false }
        } catch {}
    }
    $result = @{
        overdue = $overdue
        last_audit = if ($lastTs) { $lastTs.ToString("o") } else { "never" }
        minutes_since = if ($lastTs) { [Math]::Round(((Get-Date) - $lastTs).TotalMinutes, 1) } else { $null }
    }
    $result | ConvertTo-Json -Compress
    exit 0
}

# ── Last: read last audit entry ──
if ($Last) {
    if (Test-Path $auditFile) {
        $lastLine = Get-Content $auditFile -Tail 1
        if ($lastLine) {
            try { $entry = $lastLine | ConvertFrom-Json; $entry | ConvertTo-Json; exit 0 } catch {}
        }
    }
    Write-Output '{"status":"no audits yet"}'
    exit 0
}

# ── Submit: record audit results ──
if ($Submit) {
    $passedList = if ($Passed) { $Passed -split ',' | ForEach-Object { $_.Trim() } } else { @() }
    $failedList = if ($Failed) { $Failed -split ',' | ForEach-Object { $_.Trim() } } else { @() }

    $entry = @{
        timestamp = (Get-Date -Format "o")
        passed = $passedList
        failed = $failedList
        overall = if ($failedList.Count -eq 0) { "pass" } else { "fail" }
        note = if ($Note) { $Note } else { "" }
    }

    # Append to audit log
    $entry | ConvertTo-Json -Compress | Add-Content $auditFile -Encoding UTF8

    # Update state file
    $state = @{ last_audit = (Get-Date -Format "o"); total = 0; streak = 0 }
    if (Test-Path $stateFile) {
        try { $prev = Get-Content $stateFile -Raw | ConvertFrom-Json; $state.total = [int]$prev.total; $state.streak = [int]$prev.streak } catch {}
    }
    $state.total++
    if ($entry.overall -eq "pass") { $state.streak++ } else { $state.streak = 0 }
    $tmpState = "$stateFile.tmp.$([Guid]::NewGuid().ToString("N").Substring(0,8))"
    try { $state | ConvertTo-Json | Set-Content $tmpState -Encoding UTF8; Move-Item -Force $tmpState $stateFile } catch {}

    # Feed KG signal
    . "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
    Write-KgSignal -Source "self-audit" -EntityName "audit-$((Get-Date).ToString('yyyyMMdd-HHmm'))" -EntityType "self-audit" -Observations @("Audit: $($entry.overall). Passed: $Passed. Failed: $Failed. Streak: $($state.streak). Note: $Note") -Priority "normal"

    Write-Output "Audit recorded: $($entry.overall) | streak=$($state.streak) | total=$($state.total)"
    if ($failedList.Count -gt 0) { Write-Output "  FAILED: $($failedList -join ', ')" }
    exit 0
}

# Default: show usage
Write-Output "self-audit.ps1 — record turn-level self-audit"
Write-Output "  -Submit -Passed Q1,Q2,... [-Failed Q4] [-Note 'why']"
Write-Output "  -Status   check if audit is overdue"
Write-Output "  -Last     show last audit entry"

