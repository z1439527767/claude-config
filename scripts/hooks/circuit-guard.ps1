# circuit-guard.ps1 — PostToolUseFailure: circuit breaker integration
# Records failures, checks circuit state, warns if OPEN
param()
$ErrorActionPreference = "Continue"

# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "circuit-guard" -EntityName "hook-circuit-guard-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("circuit-guard executed at $(Get-Date -Format 'o')") -Priority "low"
$lib = "$env:USERPROFILE\.claude\scripts\lib\circuit-breaker.ps1"
if (-not (Test-Path $lib)) { exit 0 }

# Record failure
$state = & pwsh -ExecutionPolicy Bypass -File $lib -Action record_failure 2>$null

# Check if we should warn
$check = & pwsh -ExecutionPolicy Bypass -File $lib -Action check 2>$null
if ($check -eq "OPEN") {
    Write-Output "CIRCUIT_OPEN: Too many failures. Consider pausing or switching strategy."
}

exit 0
