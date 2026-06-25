# auto-compact.ps1 — PostToolUse: monitor context pressure, trigger autonomous compact
# Runs after every tool use. When pressure > 85%, signals compact needed.
param()
$ErrorActionPreference = "Continue"

$baseDir = "$env:USERPROFILE\.claude"
$guardState = "$baseDir\.claude\context_guard_state.json"

# Estimate current context load
$claudeMd = "$baseDir\CLAUDE.md"
$rulesDir = "$baseDir\.claude\rules"
$memIndex = "$baseDir\projects\C--Users-z1439--claude\memory\MEMORY.md"

$l0Tokens = 0
if (Test-Path $claudeMd) { $l0Tokens += [math]::Round((Get-Item $claudeMd).Length / 3) }
if (Test-Path "$baseDir\AGENTS.md") { $l0Tokens += [math]::Round((Get-Item "$baseDir\AGENTS.md").Length / 3) }
if (Test-Path $rulesDir) {
    Get-ChildItem $rulesDir -Filter "*.md" | ForEach-Object { $l0Tokens += [math]::Round($_.Length / 3) }
}
if (Test-Path $memIndex) { $l0Tokens += [math]::Round((Get-Item $memIndex).Length / 3) }

$budget = 200000
$ratio = $l0Tokens / $budget

# Save state
$state = @{
    last_check = (Get-Date -Format "o")
    estimated_tokens = $l0Tokens
    ratio = [math]::Round($ratio, 2)
    budget = $budget
}
$state | ConvertTo-Json -Compress | Set-Content $guardState -Encoding UTF8

# Thresholds
$COMPACT_LINE = 0.85
$WARNING_LINE = 0.75

if ($ratio -ge $COMPACT_LINE) {
    # Critical: signal compact needed
    $flagFile = "$baseDir\.claude\compact_needed.flag"
    (Get-Date -Format "o") | Set-Content $flagFile -Encoding UTF8

    $warning = @"
⚠️  CONTEXT PRESSURE: $($ratio.ToString('P0')) — AUTO-COMPACT RECOMMENDED
    Tokens: ~$l0Tokens / $budget
    Action: /compact now to prevent context overflow
    Auto-flag written: compact_needed.flag
"@
    Write-Output $warning
}

if ($ratio -ge $WARNING_LINE -and $ratio -lt $COMPACT_LINE) {
    Write-Output "CONTEXT: $($ratio.ToString('P0')) — approaching compact threshold"
}
