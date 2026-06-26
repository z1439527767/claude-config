# track-reads.ps1 — PostToolUse on Read: record what files were read
param()
$ErrorActionPreference = "Continue"
$perfHookName = "track-reads"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "track-reads" -EntityName "hook-track-reads-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("track-reads executed at $(Get-Date -Format 'o')") -Priority "low"
$toolName = $env:CLAUDE_TOOL_NAME
if ($toolName -ne "Read") { Write-PerfLog 0; exit 0 }

$trackFile = "$env:USERPROFILE\.claude\.claude\recently_read.json"
$recentlyRead = @{}
if (Test-Path $trackFile) {
    try { $recentlyRead = Get-Content $trackFile -Raw | ConvertFrom-Json } catch {}
}

# Extract file path from tool input
$toolInput = $env:CLAUDE_TOOL_INPUT
if ($toolInput) {
    try {
        $parsed = $toolInput | ConvertFrom-Json
        $fp = $parsed.file_path
        if ($fp) {
            $normalized = $fp.Replace('\', '/').ToLower()
            $recentlyRead[$normalized] = (Get-Date -Format "o")
        }
    } catch {}
}

# Prune old entries (>30min) + keep max 20
$now = Get-Date
$pruned = @{}
foreach ($k in $recentlyRead.Keys) {
    $t = try { [datetime]$recentlyRead[$k] } catch { $now }
    if (($now - $t).TotalMinutes -lt 30) { $pruned[$k] = $recentlyRead[$k] }
}
$keys = $pruned.Keys | Select-Object -Last 20
$final = @{}; foreach ($k in $keys) { $final[$k] = $pruned[$k] }

$final | ConvertTo-Json | Set-Content $trackFile -Encoding UTF8
Write-PerfLog 0; exit 0
