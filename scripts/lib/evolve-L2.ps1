# evolve-L2.ps1 — Success patterns → AGENTS.md principles
# Sourced by evolve.ps1; appends to $script:applied and $script:changes
param()

$agentsMd = "$env:USERPROFILE\.claude\AGENTS.md"
$claudeMd = "$env:USERPROFILE\.claude\CLAUDE.md"
$successFile = "$env:USERPROFILE\.claude\.claude\last_session_success.json"

if (-not (Test-Path $successFile)) { return }

try {
    $success = Get-Content $successFile -Raw | ConvertFrom-Json
    $patternFile = "$env:USERPROFILE\.claude\.claude\success_patterns.json"
    $patterns = @{}
    if (Test-Path $patternFile) { try { $patterns = Get-Content $patternFile -Raw | ConvertFrom-Json } catch {} }

    if ($success.achievements) {
        $ach = $success.achievements -join " "
        if ($ach -match "hook|脚本|script") { $patterns['hook-creation'] = [int]$patterns['hook-creation'] + 1 }
        if ($ach -match "fix|修复|bug") { $patterns['bug-fix'] = [int]$patterns['bug-fix'] + 1 }
        if ($ach -match "evolution|进化|evolve") { $patterns['evolution'] = [int]$patterns['evolution'] + 1 }
        if ($ach -match "clean|清理|删") { $patterns['cleanup'] = [int]$patterns['cleanup'] + 1 }
    }

    $principleMap = @{
        'hook-creation' = "每次新需求 → hook 优先于规则文件。Hook 是确定性执行，规则是建议。"
        'bug-fix' = "发现 bug → 立即修复 → 加 hook 防止复发 → 记录到知识图谱。不让同一个 bug 犯两次。"
        'evolution' = "进化是循环：检测 → 分析 → 应用 → 验证 → 沉淀。每步可审计。"
        'cleanup' = "清理时删多余文件，不建新系统。简单 = 少，不是多。"
    }

    foreach ($pk in @('hook-creation','bug-fix','evolution','cleanup')) {
        if ([int]$patterns[$pk] -ge 3) {
            $principle = $principleMap[$pk]
            $agentsContent = Get-Content $agentsMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if ($principle -and $agentsContent -notmatch [regex]::Escape(($principle -split '。')[0])) {
                "`n$principle" | Add-Content $agentsMd -Encoding UTF8
                $script:applied += "L2: AGENTS.md + '$pk' 原则 (x$($patterns[$pk]))"
                $patterns[$pk] = 0
            }
        }
    }
    $patterns | ConvertTo-Json | Set-Content $patternFile -Encoding UTF8

    $claudeLines = (Get-Content $claudeMd -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
    if ($claudeLines -gt 80) {
        $script:changes += "L2: CLAUDE.md $claudeLines 行 (>80), 建议清理旧规则"
    }
} catch {}
