# evolve-L3.ps1 — Performance metrics → auto-tune hook timeouts
# Sourced by evolve.ps1; appends to $script:applied
param()

$settingsJson = "$env:USERPROFILE\.claude\settings.json"
$perfDir = "$env:USERPROFILE\.claude\.claude\hook_perf"

if (-not (Test-Path $perfDir)) { return }

$settings = Get-Content $settingsJson -Raw | ConvertFrom-Json
$settingsModified = $false
$metrics = Get-HookPerfMetrics -PerfDir $perfDir -Tail 50

foreach ($hookN in $metrics.Keys) {
    $m = $metrics[$hookN]
    $found = $false
    foreach ($eventName in $settings.hooks.PSObject.Properties.Name) {
        if ($found) { break }
        foreach ($group in $settings.hooks.$eventName) {
            foreach ($h in $group.hooks) {
                if ($h.command -match [regex]::Escape($hookN)) {
                    $oldT = [int]$h.timeout
                    $newT = [math]::Max(1, [math]::Min(30, [int]($m.avgMs / 1000 * 3 + 1)))
                    if ([math]::Abs($newT - $oldT) / [math]::Max(1, $oldT) -gt 0.3) {
                        $h.timeout = $newT
                        $script:applied += "L3: $hookN timeout ${oldT}s → ${newT}s (avg $($m.avgMs.ToString('N0'))ms, max $($m.maxMs)ms)"
                        $settingsModified = $true
                    }
                    $found = $true
                    break
                }
            }
        }
    }
}

if ($settingsModified) {
    $settings | ConvertTo-Json -Depth 5 | Set-Content $settingsJson -Encoding UTF8
}
