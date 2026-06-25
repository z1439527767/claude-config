# Shared performance tracking module — used by all hook scripts
# Auto-created by L5 proactive optimization
param()
$ErrorActionPreference = "Continue"
if (-not $perfHookName) { $perfHookName = "unknown" }
$perfDir = "$env:USERPROFILE\.claude\.claude\hook_perf"
if (-not (Test-Path $perfDir)) { New-Item -ItemType Directory -Force $perfDir | Out-Null }
if (-not $sw) { $sw = [Diagnostics.Stopwatch]::StartNew() }
function Write-PerfLog { param([int]$ExitCode=0, [string]$Extra="")
  @{t=(Get-Date -Format "o");h=$perfHookName;d=$sw.ElapsedMilliseconds;e=$ExitCode}|ConvertTo-Json -Compress|Add-Content "$perfDir\$perfHookName.jsonl" -Encoding UTF8 }
