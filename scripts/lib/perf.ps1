# perf.ps1 — shared performance-logging utility
# Set $perfHookName before dot-sourcing, then call _p($exitCode) at exit points.
# Usage:
#   $perfHookName = "my-hook"
#   . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"
if (-not $perfHookName) { $perfHookName = "unknown" }
$perfSw = [Diagnostics.Stopwatch]::StartNew()
function _p($c) {
    $d = "$env:USERPROFILE\.claude\.claude\hook_perf"
    if (-not (Test-Path $d)) { mkdir -Force $d | Out-Null }
    @{
        t = (Get-Date -Format "o")
        h = $perfHookName
        d = $perfSw.ElapsedMilliseconds
        e = $c
    } | ConvertTo-Json -Compress | Add-Content "$d\$perfHookName.jsonl" -Encoding UTF8
}
