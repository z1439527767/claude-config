# post-compact-reload.ps1 — PostCompact: restore guard text as system reminder
$ErrorActionPreference = "Stop"
$perfHookName = "post-compact-reload"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
$guardFile = "$env:USERPROFILE\.claude\.claude\post_compact_guard.txt"
# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "post-compact-reload" -EntityName "hook-post-compact-reload-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("post-compact-reload executed at $(Get-Date -Format 'o')") -Priority "low"
if (Test-Path $guardFile) {
    Get-Content $guardFile -Raw | Write-Output
    Remove-Item $guardFile -Force
}
Write-PerfLog 0; exit 0
