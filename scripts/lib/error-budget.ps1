# error-budget.ps1 — SLO error budget tracking (distilled from Microsoft Agent SRE spec §4.4)
# Tracks failure rate against SLO targets, triggers burn rate alerts
param(
    [ValidateSet("record_success","record_failure","check","status","reset")]
    [string]$Action = "check",
    [double]$SloTarget = 0.995,           # 99.5% success rate target
    [int]$WindowDays = 30,
    [double]$BurnRateAlertSlow = 2.0,     # 2x normal burn → warning
    [double]$BurnRateAlertFast = 10.0     # 10x normal burn → critical
)

$budgetFile = "$env:USERPROFILE\.claude\session-env\error_budget.json"
$now = Get-Date

function Get-Budget {
    if (-not (Test-Path $budgetFile)) {
        return @{
            total_successes = 0; total_failures = 0
            window_start = $now.ToString("o")
            events = @()
        }
    }
    try { return Get-Content $budgetFile -Raw | ConvertFrom-Json } catch {
        return @{ total_successes = 0; total_failures = 0; window_start = $now.ToString("o"); events = @() }
    }
}

function Save-Budget($b) {
    # Keep events bounded at 1000
    if ($b.events.Count -gt 1000) { $b.events = @($b.events | Select-Object -Last 500) }
    $b | ConvertTo-Json -Depth 3 | Set-Content $budgetFile -Encoding UTF8
}

$budget = Get-Budget

# Reset window if expired
if ($budget.window_start) {
    $age = ($now - [datetime]$budget.window_start).TotalDays
    if ($age -gt $WindowDays) {
        $budget.total_successes = 0
        $budget.total_failures = 0
        $budget.window_start = $now.ToString("o")
        $budget.events = @()
    }
}

switch ($Action) {
    "record_success" {
        $budget.total_successes++
        $budget.events += @{ t = $now.ToString("o"); type = "success" }
        Save-Budget $budget
    }

    "record_failure" {
        $budget.total_failures++
        $budget.events += @{ t = $now.ToString("o"); type = "failure" }
        Save-Budget $budget
        # After recording failure, check burn rate
        $check = & $PSCommandPath -Action check -SloTarget $SloTarget
        if ($check.burn_alert -eq "fast") {
            Write-Output "ERROR_BUDGET: CRITICAL burn rate ${BurnRateAlertFast}x — consider circuit break"
        } elseif ($check.burn_alert -eq "slow") {
            Write-Output "ERROR_BUDGET: WARNING burn rate ${BurnRateAlertSlow}x"
        }
    }

    "check" {
        $total = $budget.total_successes + $budget.total_failures
        if ($total -lt 10) { return @{ burn_alert = "none"; error_rate = 0; remaining_budget = 1.0 } }

        $errorRate = $budget.total_failures / $total
        $errorBudget = 1.0 - $SloTarget  # e.g. 0.005 for 99.5%
        $budgetConsumed = $errorRate / $errorBudget

        # Check recent burn rate (last 1h)
        $oneHourAgo = $now.AddHours(-1).ToString("o")
        $recent = @($budget.events | Where-Object { $_.t -ge $oneHourAgo })
        $recentFails = ($recent | Where-Object { $_.type -eq "failure" }).Count
        $recentTotal = $recent.Count
        $recentErrorRate = if ($recentTotal -gt 0) { $recentFails / $recentTotal } else { 0 }
        $burnRate = if ($errorBudget -gt 0) { $recentErrorRate / $errorBudget } else { 0 }

        $alert = "none"
        if ($burnRate -ge $BurnRateAlertFast) { $alert = "fast" }
        elseif ($burnRate -ge $BurnRateAlertSlow) { $alert = "slow" }

        return @{
            burn_alert = $alert
            error_rate = [math]::Round($errorRate, 4)
            recent_error_rate = [math]::Round($recentErrorRate, 4)
            burn_rate = [math]::Round($burnRate, 2)
            budget_consumed_pct = [math]::Round($budgetConsumed * 100, 1)
            remaining_budget_pct = [math]::Round((1.0 - $budgetConsumed) * 100, 1)
            total_events = $total
        }
    }

    "status" {
        $check = & $PSCommandPath -Action check -SloTarget $SloTarget
        $budget | Select-Object total_*, window_start | ConvertTo-Json -Compress
        Write-Output ""
        $check | ConvertTo-Json -Compress
    }

    "reset" {
        Remove-Item $budgetFile -ErrorAction SilentlyContinue
        Write-Output "ERROR_BUDGET: reset"
    }
}
