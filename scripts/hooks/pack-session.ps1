# pack-session.ps1 — SessionEnd: auto-pack session summary
param()
$ErrorActionPreference = "Continue"

# Use session-summarizer if available, then pipe to data-pack
$summary = python3 "$env:USERPROFILE\.claude\scripts\session-summarizer.py" --json 2>$null
if ($LASTEXITCODE -eq 0 -and $summary) {
    $summary | python3 "$env:USERPROFILE\.claude\scripts\data-pack.py" --type session --source "session-summarizer" 2>$null
}

# Also rebuild the pack index
python3 "$env:USERPROFILE\.claude\scripts\packed-retrieve.py" --index 2>$null | Set-Content "$env:USERPROFILE\.claude\packed\INDEX.md" -Encoding UTF8

# Sync to Obsidian vault
python3 "$env:USERPROFILE\.claude\scripts\obsidian-sync.py" push 2>$null

exit 0
