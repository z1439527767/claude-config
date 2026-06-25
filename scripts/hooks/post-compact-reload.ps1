# post-compact-reload.ps1 — PostCompact: restore guard text as system reminder
$ErrorActionPreference = "Stop"
$guardFile = "$env:USERPROFILE\.claude\.claude\post_compact_guard.txt"
if (Test-Path $guardFile) {
    Get-Content $guardFile -Raw | Write-Output
    Remove-Item $guardFile -Force
}
exit 0
