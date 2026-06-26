# evolve-L1.ps1 — Multi-source friction detection → CLAUDE.md rules
# Sourced by evolve.ps1; appends to $script:applied
param()

$claudeMd = "$env:USERPROFILE\.claude\CLAUDE.md"
$frictionDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"
$failuresDir = "$env:USERPROFILE\.claude\.claude\tool_failures"
$now = Get-Date
$signals = @{}

# Source 1: Tellonce friction events
if (Test-Path $frictionDir) {
    Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        Get-Content $_.FullName -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ } |
            ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ } |
            Where-Object { $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-7) } |
            ForEach-Object {
                foreach ($s in ($_.signals -split ', ')) { if (-not $signals[$s]) { $signals[$s] = 0 }; $signals[$s]++ }
            }
    }
}

# Source 2: Tool failure patterns (broadened detection)
if (Test-Path $failuresDir) {
    Get-ChildItem $failuresDir -File -Filter "failures.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        Get-Content $_.FullName -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ } |
            ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ } |
            Where-Object { $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-7) }
    } | ForEach-Object {
        $tool = $_.tool_name; $err = $_.error
        if ($tool) { if (-not $signals["tool:$tool"]) { $signals["tool:$tool"] = 0 }; $signals["tool:$tool"]++ }
        if ($err -match 'timeout|denied|blocked|refused|not found') { $k = "sys:$($Matches[0])"; if (-not $signals[$k]) { $signals[$k] = 0 }; $signals[$k]++ }
        if (-not $signals["any_failure"]) { $signals["any_failure"] = 0 }; $signals["any_failure"]++
    }
}

# Source 3: Repeated timeout oscillation (L3 ping-pong detection)
$evoLog = "$env:USERPROFILE\.claude\.claude\evolution_log.jsonl"
if (Test-Path $evoLog) {
    $recentEvos = Get-Content $evoLog -Tail 30 -ErrorAction SilentlyContinue | Where-Object { $_ } |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ } |
        Where-Object { $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-1) }
    # Detect timeout oscillation: same hook tuned 3+ times in 24h
    $tunedHooks = @{}
    foreach ($e in $recentEvos) {
        foreach ($c in $e.changes) {
            if ($c -match 'L3: (\S+) timeout') {
                $hookName = $Matches[1]
                if (-not $tunedHooks[$hookName]) { $tunedHooks[$hookName] = 0 }; $tunedHooks[$hookName]++
            }
        }
    }
    foreach ($h in $tunedHooks.GetEnumerator()) {
        if ($h.Value -ge 3) { $signals["oscillation:$($h.Name)"] = $h.Value }
    }
}

if ($signals.Count -eq 0) { return }

# Find strongest signal
$topSignal = ($signals.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1)
if ($topSignal.Value -lt 3) { return }

$signalName = $topSignal.Name
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
    "any_failure" = "工具失败后自动记录模式，积累3次触发规则生成"
    "oscillation" = "Timeout反复振荡的hook改用p95算法，不用avg*3"
}

$newRule = $ruleMap[$signalName]
# Auto-generate rule for tool: patterns and oscillation patterns
if (-not $newRule -and $signalName -match '^tool:(.+)') {
    $toolName = $Matches[1]
    $newRule = "工具 '$toolName' 反复失败——自动重试或fallback"
} elseif (-not $newRule -and $signalName -match '^oscillation:(.+)') {
    $hookName = $Matches[1]
    $newRule = "Hook '$hookName' timeout反复振荡——硬编码p95值，不让L3自动调"
} elseif (-not $newRule -and $signalName -match '^sys:(.+)') {
    $errType = $Matches[1]
    $newRule = "系统错误 '$errType' 反复出现——添加预检和自动恢复"
}
if (-not $newRule) { return }

# Dedup: check if rule already exists
$claudeContent = Get-Content $claudeMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
if ($claudeContent -match [regex]::Escape($newRule)) { return }

# Insert rule into CLAUDE.md
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
# Atomic write: temp → rename (production rule #1)
$tmpMd = "$claudeMd.tmp.$([Guid]::NewGuid().ToString('N').Substring(0,8))"
try {
    ($claudeLines -join "`n") | Set-Content $tmpMd -Encoding UTF8 -NoNewline
    Move-Item -Force $tmpMd $claudeMd
    $script:applied += "L1: CLAUDE.md + '$newRule' (信号: '$signalName' x$($topSignal.Value), ${sources} sources)"
} catch {
    if (Test-Path $tmpMd) { Remove-Item $tmpMd -Force -ErrorAction SilentlyContinue }
}
