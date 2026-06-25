# context-budget.ps1 — SessionStart: track and report context efficiency
param()
$ErrorActionPreference = "Continue"

$budgetFile = "$env:USERPROFILE\.claude\.claude\context_budget.json"
$claudeMd = "$env:USERPROFILE\.claude\CLAUDE.md"
$agentsMd = "$env:USERPROFILE\.claude\AGENTS.md"
$localMd = "$env:USERPROFILE\.claude\CLAUDE.local.md"

# Measure context load
$claudeLines = if (Test-Path $claudeMd) { (Get-Content $claudeMd | Measure-Object -Line).Lines } else { 0 }
$agentsLines = if (Test-Path $agentsMd) { (Get-Content $agentsMd | Measure-Object -Line).Lines } else { 0 }
$localLines = if (Test-Path $localMd) { (Get-Content $localMd | Measure-Object -Line).Lines } else { 0 }

# Load rule files
$rulesDir = "$env:USERPROFILE\.claude\.claude\rules"
$ruleLines = 0
if (Test-Path $rulesDir) {
    Get-ChildItem $rulesDir -File -Filter "*.md" -ErrorAction SilentlyContinue | ForEach-Object {
        $ruleLines += (Get-Content $_.FullName | Measure-Object -Line).Lines
    }
}

# Memory entries
$memDir = "$env:USERPROFILE\.claude\projects\C--Users-z1439--claude\memory"
$memCount = 0
$memIndex = Join-Path $memDir "MEMORY.md"
if (Test-Path $memIndex) {
    $memContent = Get-Content $memIndex -Raw -Encoding UTF8
    $memCount = ([regex]::Matches($memContent, '^- \[')).Count
}

# Agent definitions
$agentsDir = "$env:USERPROFILE\.claude\.claude\agents"
$agentCount = 0
if (Test-Path $agentsDir) {
    $agentCount = (Get-ChildItem $agentsDir -File -Filter "*.md").Count
}

$totalConfigLines = $claudeLines + $agentsLines + $localLines + $ruleLines

$report = @{
    timestamp = (Get-Date -Format "o")
    claude_md_lines = $claudeLines
    agents_md_lines = $agentsLines
    local_md_lines = $localLines
    rule_lines = $ruleLines
    total_config_lines = $totalConfigLines
    memory_entries = $memCount
    agent_definitions = $agentCount
    budget_status = if ($totalConfigLines -gt 200) { "OVER" } elseif ($totalConfigLines -gt 100) { "WATCH" } else { "OK" }
    stale_memory_count = if ($memContent) { ([regex]::Matches($memContent, '\[stale\]|\[expired\]')).Count } else { 0 }
}

$report | ConvertTo-Json | Set-Content $budgetFile -Encoding UTF8

# Warning if over budget
if ($report.budget_status -eq "OVER") {
    Write-Output "CTX-BUDGET: $totalConfigLines lines in config files (>200) — consider pruning"
} elseif ($report.stale_memory_count -gt 5) {
    Write-Output "CTX-BUDGET: $($report.stale_memory_count) stale/expired memories — suggest cleanup"
}

exit 0
