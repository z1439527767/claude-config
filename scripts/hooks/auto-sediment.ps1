# auto-sediment.ps1 — Stop hook: sedimentation check + success distillation
param()

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$sw = [Diagnostics.Stopwatch]::StartNew()
function _p($c) { $d="$env:USERPROFILE\.claude\.claude\hook_perf"; if(-not(Test-Path $d)){mkdir -Force $d|Out-Null}; @{t=(Get-Date -Format "o");h="auto-sediment";d=$sw.ElapsedMilliseconds;e=$c}|ConvertTo-Json -Compress|Add-Content "$d\auto-sediment.jsonl" -Encoding UTF8 }

if ($env:STOP_HOOK_ACTIVE -eq "1") { _p 0; exit 0 }

$sessionMarker = "$env:USERPROFILE\.claude\.claude\session_start_time"
$localMd = "$env:USERPROFILE\.claude\CLAUDE.local.md"
$scriptsDir = "$env:USERPROFILE\.claude\scripts\hooks"
$settingsJson = "$env:USERPROFILE\.claude\settings.json"
$frictionDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"

# ── Determine session start time ──
$sessionStart = if (Test-Path $sessionMarker) {
    try { [datetime](Get-Content $sessionMarker -Raw).Trim() } catch { (Get-Date).AddHours(-1) }
} else {
    (Get-Date).AddHours(-1)
}

# ── Check friction events ──
$frictionCount = 0
$proposalFile = Join-Path $frictionDir "proposal_pending.json"
if (Test-Path $proposalFile) {
    try {
        $proposal = Get-Content $proposalFile -Raw | ConvertFrom-Json
        $frictionCount = $proposal.friction_count
    } catch { }
}

$notes = @()

# ── Success distillation: new scripts created ──
$newScripts = Get-ChildItem $scriptsDir -File -Filter "*.ps1" -ErrorAction SilentlyContinue |
    Where-Object { $_.CreationTime -gt $sessionStart } |
    ForEach-Object { $_.Name }

if ($newScripts.Count -gt 0) { $notes += "新 hook: $($newScripts -join ', ')" }

# ── Settings updated ──
$settingsModified = (Get-Item $settingsJson).LastWriteTime -gt $sessionStart
if ($settingsModified) { $notes += "settings.json 已更新" }

# ── CLAUDE.local.md updated (sedimentation) ──
$localMdUpdated = (Get-Item $localMd).LastWriteTime -gt $sessionStart
if ($localMdUpdated) { $notes += "CLAUDE.local.md 已沉淀" }

# ── Write success marker for next session ──
if ($notes.Count -gt 0) {
    @{
        timestamp = (Get-Date -Format "o")
        achievements = $notes
        new_scripts = $newScripts
        friction_events = $frictionCount
    } | ConvertTo-Json | Set-Content "$env:USERPROFILE\.claude\.claude\last_session_success.json" -Encoding UTF8
}

# ── Cleanup ──
Remove-Item $sessionMarker -Force -ErrorAction SilentlyContinue
Remove-Item $proposalFile -Force -ErrorAction SilentlyContinue

# ── Report ──
if ($notes.Count -gt 0) {
    Write-Output "SESSION END: $($notes -join '; ')"
}
if (-not $localMdUpdated) {
    Write-Output "SESSION END: CLAUDE.local.md 未更新 — 有值得沉淀的吗？"
}
if ($frictionCount -ge 2) {
    Write-Output "WARNING: 本会话 $frictionCount 次纠正 — 建议检查是否需要更新规则"
}

_p 0; exit 0
