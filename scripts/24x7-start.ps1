# 24x7-start.ps1 — Launch continuous autonomous operation
# Three-layer architecture:
#   L1: Windows Task Scheduler (OS-level, survives reboot)
#   L2: Claude CronCreate (session-level, 10min intervals)
#   L3: ScheduleWakeup (adaptive, cache-aware)
param(
    [int]$DurationHours = 5,
    [int]$IntervalMinutes = 15,
    [switch]$InstallOnly
)

$base = "$env:USERPROFILE\.claude"
Write-Output "=== 24/7 Autonomous Framework Bootstrap ==="
Write-Output "Duration: ${DurationHours}h | Interval: ${IntervalMinutes}min"
Write-Output ""

# ── L1: OS-Level Persistence ──
$taskName = "ClaudeAutoEvolve"
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "L1: Removed old scheduled task"
}

$action = New-ScheduledTaskAction -Execute "pwsh" `
    -Argument "-ExecutionPolicy Bypass -File `"$base\scripts\headless-run.ps1`" -Mission auto-evolve -MaxTurns 30"
$trigger = New-ScheduledTaskTrigger -Once `
    -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Hours $DurationHours)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Description "24/7 Framework Evolution" -Force | Out-Null
Write-Output "L1: Windows Task Scheduler — every ${IntervalMinutes}min for ${DurationHours}h"
Write-Output "    Task: $taskName"

# ── L2: Session Cron ──
# (created by Claude via CronCreate tool)
Write-Output "L2: Claude CronCreate — every 10min (session lifetime)"
Write-Output "L3: ScheduleWakeup — adaptive 3-30min (cache-aware)"

# ── State files ──
$files = @(
    "$base\.claude\MISSION.md",
    "$base\.claude\handoff.md",
    "$base\.claude\headless_logs"
)
foreach ($f in $files) {
    if (Test-Path $f) { Write-Output "STATE: $f — READY" }
    else { Write-Output "STATE: $f — MISSING" }
}

# ── Verify headless works ──
Write-Output ""
Write-Output "=== Verification ==="
$scriptsOk = $true
Get-ChildItem "$base\scripts\hooks\*.ps1" | ForEach-Object {
    $nullVar = $null; $pe = @()
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$nullVar, [ref]$pe)
    if ($pe.Count -gt 0) { Write-Output "SYNTAX FAIL: $($_.Name)"; $scriptsOk = $false }
}
if ($scriptsOk) { Write-Output "SYNTAX: All scripts PASS" }

$settingsOk = $true
try { Get-Content "$base\settings.json" -Raw | ConvertFrom-Json | Out-Null } catch { $settingsOk = $false }
Write-Output "JSON: settings.json $($settingsOk ? 'PASS' : 'FAIL')"

Write-Output ""
Write-Output "=== Ready for 24/7 operation ==="
Write-Output "Next OS-level run: $(Get-Date).AddMinutes(2)"
Write-Output "Handoff: $base\.claude\handoff.md"
Write-Output "Logs: $base\.claude\headless_logs\"
