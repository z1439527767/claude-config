# git-snapshot.ps1 — Auto-commit config files as rollback point (Lifeline)
param(
    [string]$Message = "manual"
)

$ErrorActionPreference = "Continue"
$perfHookName = "git-snapshot"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$claudeDir = "$env:USERPROFILE\.claude"
$snapshotLog = "$env:USERPROFILE\.claude\.claude\snapshot_log.jsonl"
$files = @("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "settings.json", "scripts/")

try {
    Push-Location $claudeDir

    # Initialize .gitignore if missing — track only the three config files
    $gitignore = "$claudeDir\.gitignore"
    $expectedIgnore = '/*
!/CLAUDE.md
!/AGENTS.md
!/settings.json'
    if (-not (Test-Path $gitignore)) {
        $expectedIgnore | Set-Content $gitignore -Encoding UTF8
    }

    # Ensure it's a git repo
    $isRepo = & git rev-parse --git-dir 2>&1
    if ($LASTEXITCODE -ne 0) {
        & git init 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "git init failed" }
    }

    # Configure local git identity if not set (for commit metadata)
    $userName = & git config user.name 2>&1
    if ($LASTEXITCODE -ne 0 -or -not $userName) {
        & git config user.name "claude-snapshot"
        & git config user.email "snapshot@claude.local"
    }

    # Stage the three config files
    & git add CLAUDE.md CLAUDE.local.md AGENTS.md settings.json scripts/ 2>&1 | Out-Null

    # Check if there are staged changes
    & git diff --cached --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        $commitMsg = "snapshot: $Message"
        & git commit -m $commitMsg 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $sha = (& git rev-parse HEAD).Trim()
            $entry = @{
                timestamp = (Get-Date -Format "o")
                message   = $Message
                commit    = $sha
            }
            # Ensure snapshot log directory exists
            $snapshotDir = Split-Path $snapshotLog -Parent
            if (-not (Test-Path $snapshotDir)) { New-Item -ItemType Directory -Force $snapshotDir | Out-Null }
            try { python "$env:USERPROFILE\.claude\scripts\adapter-db.py" insert snapshot_log "" $entry 2>$null | Out-Null } catch {
                $entry | ConvertTo-Json -Compress | Add-Content $snapshotLog -Encoding UTF8
            }
        }
    }
} catch {
    # Never block on snapshot failure — swallow
}

try { Pop-Location } catch { }

Write-PerfLog 0; exit 0
