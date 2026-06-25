# Shared performance tracking module — used by all hook scripts
# Auto-created by L5 proactive optimization
param()
$ErrorActionPreference = "Continue"
if (-not $perfHookName) { $perfHookName = "unknown" }
$perfDir = "$env:USERPROFILE\.claude\.claude\hook_perf"
if (-not (Test-Path $perfDir)) { New-Item -ItemType Directory -Force $perfDir | Out-Null }
if (-not $sw) { $sw = [Diagnostics.Stopwatch]::StartNew() }
$script:DbAdapter = "$env:USERPROFILE\.claude\scripts\adapter-db.py"

function Write-PerfLog { param([int]$ExitCode=0, [string]$Extra="")
  $json = @{t=(Get-Date -Format "o");h=$perfHookName;d=$sw.ElapsedMilliseconds;e=$ExitCode} | ConvertTo-Json -Compress
  try { python3 $script:DbAdapter insert hook_perf $perfHookName $json 2>$null | Out-Null } catch {
    # Emergency fallback: write JSONL if DB fails
    $json | Add-Content "$perfDir\$perfHookName.jsonl" -Encoding UTF8
  }
}

function Get-HookPerfMetrics {
  <#
    .SYNOPSIS
      Parse all hook_perf JSONL files and return structured perf metrics as a hashtable.
    .PARAMETER PerfDir
      Directory containing *.jsonl files. Defaults to $script:perfDir if defined, else USERPROFILE\.claude\.claude\hook_perf.
    .PARAMETER MinEntries
      Minimum valid entries required before a hook is included in results (default 10).
    .PARAMETER Tail
      Number of recent lines to read from each file (default 50).
    .OUTPUTS
      Hashtable: hookName -> @{ avgMs, maxMs, entryCount }
  #>
  param(
    [string]$PerfDir = $(if ($script:perfDir) { $script:perfDir } else { "$env:USERPROFILE\.claude\.claude\hook_perf" }),
    [int]$MinEntries = 10,
    [int]$Tail = 50
  )
  $result = @{}
  if (-not (Test-Path $PerfDir)) { return $result }
  Get-ChildItem $PerfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
    $hookN = $_.BaseName
    $lines = Get-Content $_.FullName -Tail $Tail -ErrorAction SilentlyContinue | Where-Object { $_ }
    $entries = @($lines | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ })
    if ($entries.Count -lt $MinEntries) { return }
    $durations = @($entries | ForEach-Object {
      if ($_.duration_ms) { [int]$_.duration_ms } elseif ($_.d) { [int]$_.d } else { 0 }
    } | Where-Object { $_ -gt 0 })
    if ($durations.Count -lt $MinEntries) { return }
    $result[$hookN] = @{
      avgMs      = ($durations | Measure-Object -Average).Average
      maxMs      = ($durations | Measure-Object -Maximum).Maximum
      entryCount = $durations.Count
    }
  }
  return $result
}
