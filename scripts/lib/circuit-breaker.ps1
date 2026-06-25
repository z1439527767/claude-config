# circuit-breaker.ps1 — 3-state circuit breaker (distilled from Microsoft Agent SRE spec)
# States: CLOSED → OPEN → HALF_OPEN → CLOSED (or back to OPEN)
# Sourced by hooks to detect failure cascades and auto-stop before damage
param(
    [ValidateSet("record_success","record_failure","check","reset","status")]
    [string]$Action = "check",
    [int]$FailureThreshold = 5,
    [int]$SuccessThreshold = 3,
    [int]$WindowSeconds = 300,
    [int]$CooldownSeconds = 60
)

$stateFile = "$env:USERPROFILE\.claude\session-env\circuit_breaker.json"
$now = Get-Date

function Get-State {
    if (-not (Test-Path $stateFile)) {
        return @{
            state = "CLOSED"
            failure_count = 0
            success_count = 0
            last_failure = $null
            last_state_change = $now.ToString("o")
            opened_at = $null
            total_failures = 0
            total_successes = 0
        }
    }
    try { return Get-Content $stateFile -Raw | ConvertFrom-Json } catch {
        return @{ state = "CLOSED"; failure_count = 0; success_count = 0 }
    }
}

function Save-State($s) {
    $s | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8
}

$state = Get-State

# Expire old failures
if ($state.last_failure) {
    $age = ($now - [datetime]$state.last_failure).TotalSeconds
    if ($age -gt $WindowSeconds) {
        $state.failure_count = 0
        $state.success_count = 0
    }
}

switch ($Action) {
    "record_failure" {
        $state.failure_count++
        $state.total_failures++
        $state.last_failure = $now.ToString("o")
        $state.success_count = 0

        if ($state.state -eq "HALF_OPEN") {
            $state.state = "OPEN"
            $state.opened_at = $now.ToString("o")
            $state.last_state_change = $now.ToString("o")
            Write-Output "CIRCUIT: HALF_OPEN → OPEN (trial failed)"
        } elseif ($state.state -eq "CLOSED" -and $state.failure_count -ge $FailureThreshold) {
            $state.state = "OPEN"
            $state.opened_at = $now.ToString("o")
            $state.last_state_change = $now.ToString("o")
            Write-Output "CIRCUIT: CLOSED → OPEN ($($state.failure_count) failures in ${WindowSeconds}s)"
        }
        Save-State $state
    }

    "record_success" {
        $state.success_count++
        $state.total_successes++

        if ($state.state -eq "HALF_OPEN" -and $state.success_count -ge $SuccessThreshold) {
            $state.state = "CLOSED"
            $state.failure_count = 0
            $state.success_count = 0
            $state.last_state_change = $now.ToString("o")
            Write-Output "CIRCUIT: HALF_OPEN → CLOSED (recovered)"
        }
        Save-State $state
    }

    "check" {
        if ($state.state -eq "OPEN") {
            if ($state.opened_at) {
                $openDuration = ($now - [datetime]$state.opened_at).TotalSeconds
                if ($openDuration -ge $CooldownSeconds) {
                    $state.state = "HALF_OPEN"
                    $state.failure_count = 0
                    $state.success_count = 0
                    $state.last_state_change = $now.ToString("o")
                    Save-State $state
                    Write-Output "CIRCUIT: OPEN → HALF_OPEN (cooldown elapsed)"
                    return "HALF_OPEN"
                }
            }
            Write-Output "CIRCUIT: OPEN (blocked, $([int]($CooldownSeconds - ($now - [datetime]$state.opened_at).TotalSeconds))s remaining)"
            return "OPEN"
        }
        return $state.state
    }

    "reset" {
        Remove-Item $stateFile -ErrorAction SilentlyContinue
        Write-Output "CIRCUIT: reset to CLOSED"
    }

    "status" {
        $state | ConvertTo-Json -Compress
    }
}
