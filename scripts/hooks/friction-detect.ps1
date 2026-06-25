# friction-detect.ps1 v2 — UserPromptSubmit: semantic + multilingual correction detection
param(
    [string]$prompt = ""
)
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$perfHookName = "friction-detect"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

if (-not $prompt) { exit 0 }

# ── Multi-language correction signals ──
$signals = @{
    # Chinese
    "错了" = "correction"; "不对" = "correction"; "不是这样" = "correction"
    "又" = "recurrence"; "再次" = "recurrence"; "还是" = "recurrence"
    "别" = "stop"; "不要" = "stop"; "停" = "stop"; "搞错" = "correction"
    "重新" = "retry"; "再来" = "retry"; "纠正" = "correction"; "修正" = "correction"
    "改回去" = "rollback"; "回退" = "rollback"; "撤销" = "rollback"
    "太复杂" = "simplify"; "太慢" = "slow"; "太吵" = "noise"
    # English
    "wrong" = "correction"; "incorrect" = "correction"; "mistake" = "correction"
    "no\b" = "stop"; "don't" = "stop"; "stop" = "stop"
    "again" = "recurrence"; "still" = "recurrence"
    "redo" = "retry"; "retry" = "retry"; "revert" = "rollback"
    "too complex" = "simplify"; "too slow" = "slow"; "too noisy" = "noise"
    # Pattern-based
    "\b不\b" = "negation"; "\b别\b" = "negation"
}

$matched = @()
$categories = @{}
foreach ($sig in $signals.Keys) {
    if ($prompt -match $sig) {
        $matched += $sig
        $cat = $signals[$sig]
        if (-not $categories[$cat]) { $categories[$cat] = 0 }
        $categories[$cat]++
    }
}
if ($matched.Count -eq 0) { exit 0 }

# ── Record friction event ──
$frictionDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"
if (-not (Test-Path $frictionDir)) { New-Item -ItemType Directory -Force $frictionDir | Out-Null }

$event = @{
    timestamp = (Get-Date -Format "o")
    signals   = $matched -join ", "
    categories = ($categories.Keys -join ", ")
    prompt_snippet = if ($prompt.Length -gt 200) { $prompt.Substring(0, 200) + "…" } else { $prompt }
} | ConvertTo-Json -Compress

$logFile = Join-Path $frictionDir "events.jsonl"
Add-Content -Path $logFile -Value $event -Encoding UTF8

# ── Count recent events ──
$recent = Get-Content $logFile -Tail 30 -ErrorAction SilentlyContinue |
    ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
    Where-Object { $_.timestamp -and ([datetime]$_.timestamp) -gt (Get-Date).AddHours(-4) }

# ── Escalation: same category 2+ times → flag ──
$catCounts = @{}
foreach ($r in $recent) {
    foreach ($c in ($r.categories -split ', ')) {
        if (-not $catCounts[$c]) { $catCounts[$c] = 0 }
        $catCounts[$c]++
    }
}

$escalatedCategories = $catCounts.GetEnumerator() | Where-Object { $_.Value -ge 2 }
if ($escalatedCategories.Count -gt 0) {
    $proposalFile = Join-Path $frictionDir "proposal_pending.json"
    $topCat = ($escalatedCategories | Sort-Object Value -Descending | Select-Object -First 1).Name
    $actionMap = @{
        "correction" = "用户频繁纠正 — 建议检查 CLAUDE.md 规则是否遗漏"
        "recurrence" = "重复问题 — 之前修的没彻底，找根因"
        "stop"       = "用户频繁叫停 — 可能过度执行或方向错误"
        "retry"      = "频繁重来 — 第一次方案质量不够"
        "rollback"   = "频繁回退 — 改动过于激进"
        "simplify"   = "用户觉得太复杂 — 减少输出，直接动手"
        "slow"       = "太慢 — 减少并行等待，优化脚本"
        "noise"      = "太吵 — 减少 hook 输出噪音"
        "negation"   = "否定反馈 — 方向错误，调整理解"
    }
    $action = $actionMap[$topCat] ?? "用户 $($recent.Count) 次纠正 — 需要调整"
    @{ friction_count = $recent.Count; category = $topCat; action = $action; recent = @($recent | Select-Object -Last 3) } |
        ConvertTo-Json -Depth 3 | Set-Content $proposalFile -Encoding UTF8
}

exit 0
