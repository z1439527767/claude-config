# quick-evolve.ps1 — Stop: lightweight mid-session evolution (L3 only)
# Runs in background, exits fast if nothing to tune
param()
$ErrorActionPreference = "Continue"

# Gate: minimum 30min between quick evolutions
$gateFile = "$env:USERPROFILE\.claude\.claude\quick_evo_gate.json"
$now = Get-Date
if (Test-Path $gateFile) {
    try {
        $gate = Get-Content $gateFile -Raw | ConvertFrom-Json
        $lastQuick = [datetime]$gate.last_quick_evo
        if (($now - $lastQuick).TotalMinutes -lt 30) { exit 0 }
    } catch {}
}

# Quick L3: check perf data and tune timeouts
$perfDir = "$env:USERPROFILE\.claude\.claude\hook_perf"
$settingsJson = "$env:USERPROFILE\.claude\settings.json"
if (-not (Test-Path $perfDir)) { exit 0 }

try { $settings = Get-Content $settingsJson -Raw | ConvertFrom-Json } catch { exit 0 }
$tuned = @()
$settingsModified = $false

Get-ChildItem $perfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
    $hookN = $_.BaseName
    $lines = Get-Content $_.FullName -Tail 30 -ErrorAction SilentlyContinue | Where-Object { $_ }
    $entries = @($lines | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ })
    if ($entries.Count -lt 10) { return }

    $durations = @($entries | ForEach-Object {
        if ($_.duration_ms) { [int]$_.duration_ms } elseif ($_.d) { [int]$_.d } else { 0 }
    } | Where-Object { $_ -gt 0 })
    if ($durations.Count -lt 10) { return }

    $avgMs = ($durations | Measure-Object -Average).Average
    $maxMs = ($durations | Measure-Object -Maximum).Maximum
    if ($avgMs -lt 50) { return }  # Too fast to need tuning

    # Find and tune
    foreach ($eventName in $settings.hooks.PSObject.Properties.Name) {
        foreach ($group in $settings.hooks.$eventName) {
            foreach ($h in $group.hooks) {
                if ($h.command -match [regex]::Escape($hookN)) {
                    $oldT = [int]$h.timeout
                    $newT = [math]::Max(1, [math]::Min(30, [int]($avgMs / 1000 * 3 + 1)))
                    if ([math]::Abs($newT - $oldT) / [math]::Max(1, $oldT) -gt 0.3) {
                        # Quick-evo is more conservative: only tune downwards, never increase
                        if ($newT -lt $oldT) {
                            $h.timeout = $newT
                            $tuned += "$hookN ${oldT}s→${newT}s"
                            $settingsModified = $true
                        }
                    }
                    break
                }
            }
        }
    }
}

if ($settingsModified) {
    # Quick verify before write
    $settings | ConvertTo-Json -Depth 5 | Set-Content $settingsJson -Encoding UTF8
    try { Get-Content $settingsJson -Raw | ConvertFrom-Json | Out-Null } catch {
        # Revert
        $settings.hooks = (Get-Content $settingsJson -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -ErrorAction SilentlyContinue).hooks
        exit 0
    }
    # Log
    $evolveLog = "$env:USERPROFILE\.claude\.claude\evolution_log.jsonl"
    @{ timestamp = (Get-Date -Format "o"); type = "quick-evolution"; changes = @("L3-quick: $($tuned -join ', ')") } |
        ConvertTo-Json -Compress | Add-Content $evolveLog -Encoding UTF8
}

# Update gate
@{ last_quick_evo = (Get-Date -Format "o") } | ConvertTo-Json | Set-Content $gateFile -Encoding UTF8
exit 0
