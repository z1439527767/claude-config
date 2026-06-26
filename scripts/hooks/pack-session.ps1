# pack-session.ps1 — SessionEnd: auto-pack session summary
param()
$ErrorActionPreference = "Continue"

# Use session-summarizer if available, then pipe to data-pack
# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "pack-session" -EntityName "hook-pack-session-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("pack-session executed at $(Get-Date -Format 'o')") -Priority "low"
$summary = python "$env:USERPROFILE\.claude\scripts\session-summarizer.py" --json 2>$null
if ($LASTEXITCODE -eq 0 -and $summary) {
    $summary | python "$env:USERPROFILE\.claude\scripts\data-pack.py" --type session --source "session-summarizer" 2>$null
}

# Also rebuild the pack index
python "$env:USERPROFILE\.claude\scripts\packed-retrieve.py" --index 2>$null | Set-Content "$env:USERPROFILE\.claude\packed\INDEX.md" -Encoding UTF8

# Sync to Obsidian vault
python "$env:USERPROFILE\.claude\scripts\obsidian-sync.py" push 2>$null

exit 0
