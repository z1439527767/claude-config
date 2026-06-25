# auto-distill.ps1 — SessionStart: distill 3+ same-topic memories into principles
param()
$ErrorActionPreference = "Continue"

$memDir = "$env:USERPROFILE\.claude\projects\C--Users-z1439--claude\memory"
$memIndex = Join-Path $memDir "MEMORY.md"
$agentsMd = "$env:USERPROFILE\.claude\AGENTS.md"
$distillState = "$env:USERPROFILE\.claude\.claude\distill_state.json"

if (-not (Test-Path $memIndex)) { exit 0 }

# Parse MEMORY.md entries
$lines = (Get-Content $memIndex -Raw -Encoding UTF8) -split "`n"
$entries = @()
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^- \[(\S+)\]\(([^)]+)\) — (.+?)\s\[.+?\]$') {
        $entries += @{
            id = $Matches[1]
            path = $Matches[2]
            description = $Matches[3]
            fullPath = Join-Path $memDir $Matches[2]
        }
    }
}

if ($entries.Count -lt 3) { exit 0 }

# Load state to track which groups we've already distilled
$state = @{ distilled_groups = @{} }
if (Test-Path $distillState) {
    try { $state = Get-Content $distillState -Raw | ConvertFrom-Json } catch { }
}

# Categorize entries by keyword similarity
$groups = @{}
foreach ($e in $entries) {
    $desc = $e.description.ToLower()
    $category = "other"
    if ($desc -match 'hook|preToolUse|session|事件') { $category = 'hooks' }
    elseif ($desc -match 'memory|记忆|遗忘|蒸馏|decay') { $category = 'memory' }
    elseif ($desc -match 'error|bug|错误|bug') { $category = 'bugs' }
    elseif ($desc -match 'clean|清理|delete|删除') { $category = 'cleanup' }
    elseif ($desc -match 'rule|规则|principle|原则|行为') { $category = 'rules' }
    elseif ($desc -match 'verify|验证|test|测试') { $category = 'verification' }
    if (-not $groups[$category]) { $groups[$category] = @() }
    $groups[$category] += $e
}

# Check each group for distillation threshold (3+)
$distilled = @()
foreach ($cat in $groups.Keys) {
    $members = $groups[$cat]
    if ($members.Count -lt 3) { continue }
    if ($state.distilled_groups[$cat] -and [int]$state.distilled_groups[$cat] -ge $members.Count) { continue }

    # Generate principle from the group
    $principleMap = @{
        'hooks'    = "每次重复问题 → 加 hook 防护而非口头规则。Hook 是确定性执行的唯一保障。"
        'memory'   = "记忆需要衰减和蒸馏。>30天未访问 = aging, >60天 = stale, >90天 = 删除或归档。"
        'bugs'     = "Bug 修复三步骤：修代码 → 加 hook 防复发 → 写知识图谱记录根因。缺一不可。"
        'cleanup'  = "清理 = 删多余文件。不建新系统、不加新抽象。简单 > 完备。"
        'rules'    = "行为规则用否定约束（不能做什么），不用正面指令（应该做什么）。否定约束更精准。"
        'verification' = "验证用外部手段（exit code、文件内容），自我感觉不算。没验证 = 没完成。"
    }

    $principle = $principleMap[$cat]
    if (-not $principle) { continue }

    $agentsContent = Get-Content $agentsMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    $keySentence = ($principle -split '[。.]')[0]
    if ($agentsContent -notmatch [regex]::Escape($keySentence.Substring(0, [Math]::Min(20, $keySentence.Length)))) {
        "`n$principle" | Add-Content $agentsMd -Encoding UTF8
        $distilled += "$cat ($($members.Count) memories → 1 principle)"
    }

    $state.distilled_groups[$cat] = $members.Count
}

if ($distilled.Count -gt 0) {
    $state | ConvertTo-Json | Set-Content $distillState -Encoding UTF8
    Write-Output "DISTILL: $($distilled -join '; ')"
}

# ── Cross-session quality trend analysis ──
$trendFile = "$env:USERPROFILE\.claude\.claude\session_history\quality_trend.jsonl"
if (Test-Path $trendFile) {
    $sessions = Get-Content $trendFile -Tail 10 -Encoding UTF8 -ErrorAction SilentlyContinue |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ }
    if ($sessions.Count -ge 3) {
        $scores = @($sessions | ForEach-Object { $_.score })
        $avgScore = ($scores | Measure-Object -Average).Average
        $trend = if ($scores[-1] -gt $avgScore) { "improving" }
                 elseif ($scores[-1] -lt $avgScore) { "declining" }
                 else { "stable" }

        if ($trend -eq "declining" -and $scores.Count -ge 5) {
            $last3 = ($scores[-3..-1] | Measure-Object -Average).Average
            $first3 = ($scores[0..2] | Measure-Object -Average).Average
            if ($last3 -lt $first3 - 10) {
                Write-Output "TREND: quality declining ($($first3:N0) → $($last3:N0)) — consider pruning rules or reducing friction"
            }
        }
        if ($trend -eq "improving") {
            Write-Output "TREND: quality improving ($($scores[0]) → $($scores[-1]))"
        }
    }
}
exit 0
