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
        if ($hoursSince -lt 0.008) {
            $script:canEvolve = $false
            $script:gateReason = "距上次进化 ${hoursSince}h < 30s"
        }
        $recentEvos = ($gate.recent_evo_timestamps | ForEach-Object { [datetime]$_ }) |
            Where-Object { ($now - $_).TotalDays -lt 7 }
        if (($recentEvos | Measure-Object).Count -ge 20) {
            $script:canEvolve = $false
            $script:gateReason = "7天内已进化 20 次"
        }
    } catch { $script:canEvolve = $true }
}

if ($script:canEvolve) {
    # Pre-evo safety net: backup core files before any mutation
    $backupDir = "$env:USERPROFILE\.claude\.claude\evo_backups"
    if (-not (Test-Path $backupDir)) { try { New-Item -ItemType Directory -Force $backupDir | Out-Null } catch {} }
    $ts = (Get-Date -Format "yyyyMMdd_HHmmss")
    @("$env:USERPROFILE\.claude\settings.json", "$env:USERPROFILE\.claude\CLAUDE.md", "$env:USERPROFILE\.claude\AGENTS.md") | ForEach-Object {
        if (Test-Path $_) { try { Copy-Item $_ (Join-Path $backupDir "$(Split-Path $_ -Leaf).$ts.bak") -Force -ErrorAction SilentlyContinue } catch {} }
    }
    # Keep only last 10 backups
    Get-ChildItem $backupDir -File -Filter "*.bak" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -Skip 10 |
        ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }

    $snapshotScript = "$env:USERPROFILE\.claude\scripts\hooks\git-snapshot.ps1"
    if (Test-Path $snapshotScript) {
        & pwsh -ExecutionPolicy Bypass -File $snapshotScript -Message "pre-evolution" 2>&1 | Out-Null
    }
}
