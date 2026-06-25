# evolve-gate.ps1 — evolution gate + pre-evo snapshot
# Sourced by evolve.ps1; sets $canEvolve, $gateReason, and takes pre-evo snapshot
param()

$gateFile = "$env:USERPROFILE\.claude\.claude\evo_gate.json"
$now = Get-Date
$script:canEvolve = $true
$script:gateReason = ""

if (Test-Path $gateFile) {
    try {
        $gate = Get-Content $gateFile -Raw | ConvertFrom-Json
        $lastEvo = [datetime]$gate.last_evolution
        $hoursSince = ($now - $lastEvo).TotalHours
        if ($hoursSince -lt 0.033) {
            $script:canEvolve = $false
            $script:gateReason = "距上次进化 ${hoursSince}h < 2min"
        }
        $recentEvos = ($gate.recent_evo_timestamps | ForEach-Object { [datetime]$_ }) |
            Where-Object { ($now - $_).TotalDays -lt 7 }
        if (($recentEvos | Measure-Object).Count -ge 10) {
            $script:canEvolve = $false
            $script:gateReason = "7天内已进化 10 次"
        }
    } catch { $script:canEvolve = $true }
}

if ($script:canEvolve) {
    $snapshotScript = "$env:USERPROFILE\.claude\scripts\hooks\git-snapshot.ps1"
    if (Test-Path $snapshotScript) {
        & pwsh -ExecutionPolicy Bypass -File $snapshotScript -Message "pre-evolution" 2>$null
    }
}
