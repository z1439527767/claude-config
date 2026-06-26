# notify.ps1 — Notification hook: desktop notification + log
param()
$ErrorActionPreference = "Continue"
$perfHookName = "notify"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "notify" -EntityName "hook-notify-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("notify executed at $(Get-Date -Format 'o')") -Priority "low"
# ── Read notification context from stdin ──
$message = $null
$notificationType = "info"
try {
    $stdinRaw = $Input | Out-String
    if ($stdinRaw.Trim()) {
        $data = $stdinRaw | ConvertFrom-Json
        $message = $data.message
        $notificationType = $data.notification_type
    }
} catch {}
if (-not $message) { $message = $env:CLAUDE_NOTIFICATION_MESSAGE }
if (-not $message) { $message = "Claude Code notification" }

# ── Log to notification journal ──
$logDir = "$env:USERPROFILE\.claude\.claude\notifications"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$entry = @{ timestamp = (Get-Date -Format "o"); type = $notificationType; message = $message } | ConvertTo-Json -Compress
try { python "$env:USERPROFILE\.claude\scripts\adapter-db.py" insert notifications "" $entry 2>$null | Out-Null } catch {
    Add-Content "$logDir\notifications.jsonl" -Value $entry -Encoding UTF8
}

# ── Windows toast (Win10+ only, no extra modules) ──
try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop

    $iconPath = [System.Drawing.SystemIcons]::Information

    # Use a self-cleaning balloon tip via hidden form
    $form = New-Object System.Windows.Forms.Form
    $form.WindowState = "Minimized"
    $form.ShowInTaskbar = $false
    $form.Visible = $false

    $notifyIcon = New-Object System.Windows.Forms.NotifyIcon
    $notifyIcon.Icon = [System.Drawing.SystemIcons]::Information
    $notifyIcon.Visible = $true
    $notifyIcon.BalloonTipTitle = "Claude Code"
    $notifyIcon.BalloonTipText = if ($message.Length -gt 200) { $message.Substring(0, 200) } else { $message }
    $notifyIcon.BalloonTipIcon = "Info"
    $notifyIcon.ShowBalloonTip(3000)

    # Cleanup after 3.5s
    Start-Sleep -Milliseconds 3500
    $notifyIcon.Visible = $false
    $notifyIcon.Dispose()
    $form.Dispose()
} catch {
    # Toast failed — already logged to file, that's fine
}

Write-PerfLog 0; exit 0
