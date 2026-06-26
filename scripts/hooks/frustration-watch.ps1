# frustration-watch.ps1 — UserPromptSubmit: detect user frustration signals
# Writes structured signal report to session-env/frustration.json
param($prompt)
$ErrorActionPreference = "Continue"

# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "frustration-watch" -EntityName "hook-frustration-watch-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("frustration-watch executed at $(Get-Date -Format 'o')") -Priority "low"
if (-not $prompt -or $prompt.Length -lt 5) { exit 0 }

$reportFile = "$env:USERPROFILE\.claude\session-env\frustration.json"
$historyFile = "$env:USERPROFILE\.claude\session-env\_frustration_history.jsonl"

try {
    # Read recent history for context (last 10 messages)
    $history = @()
    if (Test-Path $historyFile) {
        $history = @(Get-Content $historyFile -Encoding UTF8 -Tail 10 | ForEach-Object {
            try { $_ | ConvertFrom-Json } catch { $null }
        } | Where-Object { $_ })
    }

    # Quick local signal detection (no Python dependency for basic check)
    $signals = @{}
    $low = $prompt.ToLower()

    # Brevity check
    if ($prompt.Length -lt 10) { $signals['brevity'] = 1.0 }
    elseif ($prompt.Length -lt 20) { $signals['brevity'] = 0.5 }
    else { $signals['brevity'] = 0.0 }

    # Imperative/commanding tone
    $politeness = @('please', 'thanks', 'thank', 'could', 'would', 'can you', '麻烦')
    $hasPoliteness = ($politeness | Where-Object { $low -match [regex]::Escape($_) }).Count -gt 0
    $words = ($prompt -split '\s+').Count
    $signals['imperative'] = if ($words -lt 6 -and -not $hasPoliteness) { 0.6 } else { 0.0 }

    # Correction words
    $corrections = @('no', 'wrong', "don't", 'dont', 'incorrect', '不是', '不对', '错了', '不', '别')
    $hasCorrection = ($corrections | Where-Object { $low -match [regex]::Escape($_) }).Count -gt 0
    $signals['correction'] = if ($hasCorrection) { 0.7 } else { 0.0 }

    # CAPS/emphasis
    $caps = ($prompt.ToCharArray() | Where-Object { $_ -match '[A-Z]' }).Count
    $total = ($prompt.ToCharArray() | Where-Object { $_ -match '[a-zA-Z]' }).Count
    $signals['caps'] = if ($total -gt 0 -and $caps / $total -gt 0.5) { 0.5 } else { 0.0 }

    # Composite score
    $weights = @{brevity=0.4; imperative=0.5; correction=0.7; caps=0.3}
    $score = 0.0
    $totalWeight = 0.0
    foreach ($k in $signals.Keys) {
        $score += $signals[$k] * $weights[$k]
        $totalWeight += $weights[$k]
    }
    $score = [Math]::Round($score / $totalWeight, 3)

    $level = switch ($score) {
        { $_ -lt 0.2 } { 'normal' }
        { $_ -lt 0.4 } { 'mild' }
        { $_ -lt 0.6 } { 'elevated' }
        { $_ -lt 0.8 } { 'high' }
        default { 'critical' }
    }

    $report = @{
        timestamp = (Get-Date -Format 'o')
        score = $score
        level = $level
        signals = $signals
    }

    $report | ConvertTo-Json -Compress | Set-Content $reportFile -Encoding UTF8

    # Log to history
    $reportJson = $report | ConvertTo-Json -Compress
    try { python "$env:USERPROFILE\.claude\scripts\adapter-db.py" insert frustration_history "" $reportJson 2>$null | Out-Null } catch {
        $reportJson | Add-Content $historyFile -Encoding UTF8
    }

    if ($level -ne 'normal') {
        Write-Output "frustration_level=$level score=$score"
    }
} catch {
    # Best-effort, never block
}
exit 0
