# post-compact-reload.ps1 — PostCompact: restore guard text as system reminder
$ErrorActionPreference = "Stop"
$perfHookName = "post-compact-reload"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
$guardFile = "$env:USERPROFILE\.claude\.claude\post_compact_guard.txt"
if (Test-Path $guardFile) {
    Get-Content $guardFile -Raw | Write-Output
    Remove-Item $guardFile -Force
}
_p 0; exit 0
