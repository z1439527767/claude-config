# evolve-L1.ps1 — Friction patterns → CLAUDE.md rules
# Sourced by evolve.ps1; appends to $script:applied
param()

$claudeMd = "$env:USERPROFILE\.claude\CLAUDE.md"
$frictionDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"
$now = Get-Date

if (-not (Test-Path $frictionDir)) { return }

$allFriction = Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue |
    ForEach-Object {
        Get-Content $_.FullName -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ } |
            ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ }
    }

$recentFriction = $allFriction | Where-Object {
    $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-7)
}

if ($recentFriction.Count -lt 2) { return }

$signalCounts = @{}
foreach ($f in $recentFriction) {
    foreach ($s in ($f.signals -split ', ')) {
        if (-not $signalCounts[$s]) { $signalCounts[$s] = 0 }
        $signalCounts[$s]++
    }
}

$hotSignals = $signalCounts.GetEnumerator() | Where-Object { $_.Value -ge 3 } | Sort-Object Value -Descending
if ($hotSignals.Count -eq 0) { return }

$topSignal = ($hotSignals | Select-Object -First 1).Name
$ruleMap = @{
    "错了" = "修改前先读文件确认当前内容"
    "不对" = "修改前先读文件确认当前内容"
    "不是这样" = "动手前先确认理解是否正确"
    "又" = "同一问题出现两次时停手找根因"
    "再次" = "同一问题出现两次时停手找根因"
    "别" = "用户说停就停，不等完成当前操作"
    "不要" = "用户说停就停，不等完成当前操作"
    "停" = "用户说停就停，不等完成当前操作"
    "重新" = "失败后换方案重试，不复用同一条路"
}

if (-not $ruleMap[$topSignal]) { return }

$newRule = $ruleMap[$topSignal]
$claudeContent = Get-Content $claudeMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
if ($claudeContent -match [regex]::Escape($newRule)) { return }

$claudeLines = @($claudeContent -split "`n")
$inserted = $false
for ($i = $claudeLines.Count - 1; $i -ge 0; $i--) {
    if ($claudeLines[$i] -match '^- ') {
        $claudeLines = @($claudeLines[0..$i]) + @("- $newRule") + @($claudeLines[($i+1)..($claudeLines.Count-1)])
        $inserted = $true
        break
    }
}
if (-not $inserted) { $claudeLines += "- $newRule" }
$claudeLines -join "`n" | Set-Content $claudeMd -Encoding UTF8 -NoNewline
$script:applied += "L1: CLAUDE.md + '$newRule' (信号: '$topSignal' x$($hotSignal.Value))"

# Track rule effectiveness
$ruleTrackFile = "$env:USERPROFILE\.claude\.claude\rule_effectiveness.json"
$ruleTrack = @{}
if (Test-Path $ruleTrackFile) { try { $ruleTrack = Get-Content $ruleTrackFile -Raw | ConvertFrom-Json } catch {} }
$ruleId = "rule_$(Get-Date -Format 'yyyyMMddHHmmss')"
$ruleTrack[$ruleId] = @{
    rule = $newRule
    signal = $topSignal
    added = (Get-Date -Format "o")
    friction_before = $recentFriction.Count
    status = "active"
}
$ruleTrack | ConvertTo-Json | Set-Content $ruleTrackFile -Encoding UTF8
