# nightly-evolve.ps1 — Local equivalent of cloud Routine "Nightly Evolution Audit"
# Run via Windows Task Scheduler: daily at 3am
param()

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$summaryDir = "$env:USERPROFILE\.claude\.claude\session_history"

# 1. Run memory scoring (Ebbinghaus decay)
Write-Output "[nightly] Running memory-score..."
$result = & pwsh -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\scripts\hooks\memory-score.ps1" -RecordAccess:$false 2>&1
Write-Output $result

# 2. Check for decay candidates
Write-Output "[nightly] Checking rule decay..."
$evolveLog = "$env:USERPROFILE\.claude\.claude\evolution_log.jsonl"
if (Test-Path $evolveLog) {
    $oldEvolutions = Get-Content $evolveLog -Tail 50 -ErrorAction SilentlyContinue |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
        Where-Object { $_ -and [datetime]$_.timestamp -lt (Get-Date).AddDays(-30) }
    if ($oldEvolutions.Count -gt 0) {
        @{
            timestamp = (Get-Date -Format "o")
            stale_rules = $oldEvolutions.Count
            oldest = ($oldEvolutions | Sort-Object { [datetime]$_.timestamp } | Select-Object -First 1).timestamp
        } | ConvertTo-Json | Set-Content "$env:USERPROFILE\.claude\.claude\decay_report.json" -Encoding UTF8
    }
}

# 3. Check for skill distillation triggers
Write-Output "[nightly] Checking skill patterns..."
$patternFile = "$env:USERPROFILE\.claude\.claude\success_patterns.json"
if (Test-Path $patternFile) {
    try {
        $patterns = Get-Content $patternFile -Raw | ConvertFrom-Json
        foreach ($key in $patterns.PSObject.Properties.Name) {
            if ($patterns.$key -ge 3) {
                Write-Output "  Pattern '$key' has $($patterns.$key) successes — skill ready to distill"
            }
        }
    } catch { }
}

# 4. Write summary
@{
    timestamp = (Get-Date -Format "o")
    type = "nightly-evolution"
    memory_scored = $true
} | ConvertTo-Json | Set-Content (Join-Path $summaryDir "nightly_$(Get-Date -Format 'yyyyMMdd').json") -Encoding UTF8

Write-Output "[nightly] Done."
