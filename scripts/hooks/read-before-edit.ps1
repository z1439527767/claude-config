# read-before-edit.ps1 — PreToolUse: block Edit/Write if file hasn't been Read
# Pattern from 60-hook framework + community best practice
param()
$ErrorActionPreference = "Continue"
$perfHookName = "read-before-edit"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$toolName = $env:CLAUDE_TOOL_NAME
$toolInput = $env:CLAUDE_TOOL_INPUT
if ($toolName -notin @("Edit", "Write")) { Write-PerfLog 0; exit 0 }

# Extract file path
$filePath = $null
try {
    $parsed = $toolInput | ConvertFrom-Json
    $filePath = $parsed.file_path
} catch {}
if (-not $filePath) { Write-PerfLog 0; exit 0 }

# Track recently read files
$trackFile = "$env:USERPROFILE\.claude\.claude\recently_read.json"
$recentlyRead = @{}
if (Test-Path $trackFile) {
    try { $recentlyRead = Get-Content $trackFile -Raw | ConvertFrom-Json } catch {}
}

# Prune entries older than 10 minutes
$now = Get-Date
$pruned = @{}
foreach ($k in $recentlyRead.Keys) {
    $t = [datetime]$recentlyRead[$k]
    if (($now - $t).TotalMinutes -lt 10) { $pruned[$k] = $recentlyRead[$k] }
}
$recentlyRead = $pruned

$normalized = $filePath.Replace('\', '/').ToLower()

if (-not $recentlyRead[$normalized]) {
    Write-Output '{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "READ-BEFORE-EDIT: File not read recently. Read it first before editing." } }'
    Write-PerfLog 2; exit 2
}

# Save updated tracker
$recentlyRead | ConvertTo-Json | Set-Content $trackFile -Encoding UTF8
Write-PerfLog 0; exit 0
