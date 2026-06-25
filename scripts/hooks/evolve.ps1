# evolve.ps1 — SessionStart: APEX 3-layer self-evolution engine v2
# L1: Friction patterns → CLAUDE.md rules (NEW)
# L2: Success patterns → AGENTS.md principles
# L3: Hook performance → auto-apply timeout tuning (UPGRADED: now writes settings.json)
param()
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$claudeMd   = "$env:USERPROFILE\.claude\CLAUDE.md"
$agentsMd   = "$env:USERPROFILE\.claude\AGENTS.md"
$settingsJson = "$env:USERPROFILE\.claude\settings.json"
$localMd    = "$env:USERPROFILE\.claude\CLAUDE.local.md"
$frictionDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"
$successFile = "$env:USERPROFILE\.claude\.claude\last_session_success.json"
$evolveLog  = "$env:USERPROFILE\.claude\.claude\evolution_log.jsonl"
$perfDir    = "$env:USERPROFILE\.claude\.claude\hook_perf"
$distillState = "$env:USERPROFILE\.claude\.claude\distill_state.json"
$memDir     = "$env:USERPROFILE\.claude\projects\C--Users-z1439--claude\memory"
$snapshotScript = "$env:USERPROFILE\.claude\scripts\hooks\git-snapshot.ps1"

$changes  = @()
$applied  = @()

# ═══════════════════════════════════════
# EVOLUTION GATE: adaptive pacing
# ═══════════════════════════════════════
$gateFile = "$env:USERPROFILE\.claude\.claude\evo_gate.json"
$now = Get-Date
$canEvolve = $true
$gateReason = ""

if (Test-Path $gateFile) {
    try {
        $gate = Get-Content $gateFile -Raw | ConvertFrom-Json
        $lastEvo = [datetime]$gate.last_evolution
        $hoursSince = ($now - $lastEvo).TotalHours
        # Active dev: 5min minimum between evolutions
        if ($hoursSince -lt 0.083) {
            $canEvolve = $false
            $gateReason = "距上次进化 ${hoursSince}h < 5min"
        }
        # Reduced from 3/week to 10/week for active development
        $recentEvos = ($gate.recent_evo_timestamps | ForEach-Object { [datetime]$_ }) |
            Where-Object { ($now - $_).TotalDays -lt 7 }
        if (($recentEvos | Measure-Object).Count -ge 10) {
            $canEvolve = $false
            $gateReason = "7天内已进化 10 次"
        }
    } catch { $canEvolve = $true }
}

if (-not $canEvolve) {
    Write-Output "EVOLVE: gated — $gateReason"
    exit 0
}

# ═══════════════════════════════════════
# PRE-EVOLUTION SNAPSHOT
# ═══════════════════════════════════════
if (Test-Path $snapshotScript) {
    & pwsh -ExecutionPolicy Bypass -File $snapshotScript -Message "pre-evolution" 2>$null
}

# ═══════════════════════════════════════
# L1: FRICTION → RULE PIPELINE (NEW)
# ═══════════════════════════════════════
if (Test-Path $frictionDir) {
    $allFriction = Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-Content $_.FullName -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ } |
                ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ }
        }

    $recentFriction = $allFriction | Where-Object {
        $_.timestamp -and ([datetime]$_.timestamp) -gt $now.AddDays(-7)
    }

    if ($recentFriction.Count -ge 2) {
        # Extract signal keywords that appear 3+ times
        $signalCounts = @{}
        foreach ($f in $recentFriction) {
            foreach ($s in ($f.signals -split ', ')) {
                if (-not $signalCounts[$s]) { $signalCounts[$s] = 0 }
                $signalCounts[$s]++
            }
        }

        $hotSignals = $signalCounts.GetEnumerator() | Where-Object { $_.Value -ge 3 } | Sort-Object Value -Descending

        if ($hotSignals.Count -gt 0) {
            $topSignal = ($hotSignals | Select-Object -First 1).Name

            # Map signals to concrete rules
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

            if ($ruleMap[$topSignal]) {
                $newRule = $ruleMap[$topSignal]
                $claudeContent = Get-Content $claudeMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
                if ($claudeContent -notmatch [regex]::Escape($newRule)) {
                    $claudeLines = @($claudeContent -split "`n")
                    # Insert before last line or append
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
                    $applied += "L1: CLAUDE.md + '$newRule' (信号: '$topSignal' x$($hotSignal.Value))"

                    # Track rule for effectiveness measurement
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
                }
            }
        }
    }
}

# ═══════════════════════════════════════
# L2: SUCCESS → PRINCIPLE DISTILLATION
# ═══════════════════════════════════════
if (Test-Path $successFile) {
    try {
        $success = Get-Content $successFile -Raw | ConvertFrom-Json

        # Track success patterns
        $patternFile = "$env:USERPROFILE\.claude\.claude\success_patterns.json"
        $patterns = @{}
        if (Test-Path $patternFile) {
            try { $patterns = Get-Content $patternFile -Raw | ConvertFrom-Json } catch { }
        }

        if ($success.achievements) {
            $ach = $success.achievements -join " "
            if ($ach -match "hook|脚本|script") { $patterns['hook-creation'] = [int]$patterns['hook-creation'] + 1 }
            if ($ach -match "fix|修复|bug") { $patterns['bug-fix'] = [int]$patterns['bug-fix'] + 1 }
            if ($ach -match "evolution|进化|evolve") { $patterns['evolution'] = [int]$patterns['evolution'] + 1 }
            if ($ach -match "clean|清理|删") { $patterns['cleanup'] = [int]$patterns['cleanup'] + 1 }
        }

        # Auto-distill when same pattern hits 3+
        foreach ($pk in @('hook-creation','bug-fix','evolution','cleanup')) {
            if ([int]$patterns[$pk] -ge 3) {
                $principleMap = @{
                    'hook-creation' = "每次新需求 → hook 优先于规则文件。Hook 是确定性执行，规则是建议。"
                    'bug-fix' = "发现 bug → 立即修复 → 加 hook 防止复发 → 记录到知识图谱。不让同一个 bug 犯两次。"
                    'evolution' = "进化是循环：检测 → 分析 → 应用 → 验证 → 沉淀。每步可审计。"
                    'cleanup' = "清理时删多余文件，不建新系统。简单 = 少，不是多。"
                }
                $principle = $principleMap[$pk]
                $agentsContent = Get-Content $agentsMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
                if ($principle -and $agentsContent -notmatch [regex]::Escape(($principle -split '。')[0])) {
                    "`n$principle" | Add-Content $agentsMd -Encoding UTF8
                    $applied += "L2: AGENTS.md + '$pk' 原则 (x$($patterns[$pk]))"
                    $patterns[$pk] = 0
                }
            }
        }
        $patterns | ConvertTo-Json | Set-Content $patternFile -Encoding UTF8

        # CLAUDE.md line limit check
        $claudeLines = (Get-Content $claudeMd -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
        if ($claudeLines -gt 80) {
            $changes += "L2: CLAUDE.md $claudeLines 行 (>80), 建议清理旧规则"
        }
    } catch { }
}

# ═══════════════════════════════════════
# L3: PERFORMANCE → AUTO-APPLY TIMEOUTS (UPGRADED)
# ═══════════════════════════════════════
if (Test-Path $perfDir) {
    $settings = Get-Content $settingsJson -Raw | ConvertFrom-Json
    $settingsModified = $false

    Get-ChildItem $perfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $hookN = $_.BaseName
        $lines = Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue | Where-Object { $_ }
        $entries = @($lines | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ })
        if ($entries.Count -lt 10) { return }

        $durations = @($entries | ForEach-Object {
            if ($_.duration_ms) { [int]$_.duration_ms }
            elseif ($_.d) { [int]$_.d }
            else { 0 }
        } | Where-Object { $_ -gt 0 })
        if ($durations.Count -lt 10) { return }

        $avgMs = ($durations | Measure-Object -Average).Average
        $maxMs = ($durations | Measure-Object -Maximum).Maximum

        # Find and update timeout in settings.json
        $found = $false
        foreach ($eventName in $settings.hooks.PSObject.Properties.Name) {
            if ($found) { break }
            foreach ($group in $settings.hooks.$eventName) {
                foreach ($h in $group.hooks) {
                    if ($h.command -match [regex]::Escape($hookN)) {
                        $oldT = [int]$h.timeout
                        # New timeout = avg * 3 converted to seconds, bounded [1, 30]
                        $newT = [math]::Max(1, [math]::Min(30, [int]($avgMs / 1000 * 3 + 1)))

                        # Only change if difference is substantial (>30%)
                        if ([math]::Abs($newT - $oldT) / [math]::Max(1, $oldT) -gt 0.3) {
                            $h.timeout = $newT
                            $applied += "L3: $hookN timeout ${oldT}s → ${newT}s (avg ${avgMs:N0}ms, max ${maxMs}ms)"
                            $settingsModified = $true
                        }
                        $found = $true
                        break
                    }
                }
            }
        }
    }

    if ($settingsModified) {
        $settings | ConvertTo-Json -Depth 5 | Set-Content $settingsJson -Encoding UTF8
    }
}

# ═══════════════════════════════════════
# L5: PROACTIVE OPTIMIZATION (NEW)
# ═══════════════════════════════════════

# 5a: Detect unused scripts (not referenced by any hook OR other script)
$scriptsDir5a = "$env:USERPROFILE\.claude\scripts\hooks"
$allScripts = @(Get-ChildItem "$scriptsDir5a\*.ps1" -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
$referencedScripts = @{}
foreach ($eventName in $settings.hooks.PSObject.Properties.Name) {
    foreach ($group in $settings.hooks.$eventName) {
        foreach ($h in $group.hooks) {
            foreach ($sn in $allScripts) {
                if ($h.command -match [regex]::Escape($sn)) { $referencedScripts[$sn] = $true }
            }
        }
    }
}
# Also check cross-script references (e.g. learn-online.ps1 called by loop-guard.ps1)
foreach ($sn in $allScripts) {
    if ($referencedScripts[$sn]) { continue }
    $pat = [regex]::Escape($sn)
    foreach ($other in $allScripts) {
        if ($other -eq $sn) { continue }
        if ((Get-Content (Join-Path $scriptsDir5a $other) -Raw -ErrorAction SilentlyContinue) -match $pat) {
            $referencedScripts[$sn] = $true
            break
        }
    }
}
$unused = $allScripts | Where-Object { -not $referencedScripts[$_] }
if ($unused.Count -gt 0) {
    $changes += "L5: $($unused.Count) unused scripts: $($unused -join ', ') — consider deleting"
}

# 5b: Detect rule redundancy (same text in CLAUDE.md + AGENTS.md)
$claudeContent = Get-Content $claudeMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
$agentsContent = Get-Content $agentsMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
if ($claudeContent -and $agentsContent) {
    $claudeLines = @($claudeContent -split "`n" | Where-Object { $_.Trim().Length -gt 20 })
    $agentsLines = @($agentsContent -split "`n" | Where-Object { $_.Trim().Length -gt 20 })
    $dupCount = 0
    foreach ($cl in $claudeLines) {
        $key = $cl.Trim().Substring(0, [Math]::Min(30, $cl.Trim().Length))
        foreach ($al in $agentsLines) {
            if ($al.Trim().Length -gt 20 -and $al.Trim().Substring(0, [Math]::Min(30, $al.Trim().Length)) -eq $key) {
                $dupCount++
            }
        }
    }
    if ($dupCount -gt 1) {
        $changes += "L5: $dupCount duplicate rules between CLAUDE.md and AGENTS.md"
    }
}

# 5c: Error pattern learning from tool_failures
$failureDir = "$env:USERPROFILE\.claude\.claude\tool_failures"
if (Test-Path $failureDir) {
    Get-ChildItem $failureDir -File -Filter "failures.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $failures = Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue |
            ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ }
        if ($failures.Count -lt 3) { return }

        # Count failure by tool — skip logging artifacts (null tool_name)
        $toolCounts = @{}
        foreach ($f in $failures) {
            if (-not $f.tool_name -or $f.tool_name -eq 'unknown' -or -not $f.tool_input) { continue }
            if (-not $toolCounts[$f.tool_name]) { $toolCounts[$f.tool_name] = 0 }
            $toolCounts[$f.tool_name]++
        }

        $hotTools = $toolCounts.GetEnumerator() | Where-Object { $_.Value -ge 3 } | Sort-Object Value -Descending
        foreach ($ht in $hotTools) {
            $changes += "L5: '$($ht.Name)' failed $($ht.Value) times — consider adding retry or fallback"
        }
    }
}

# 5d: Rule effectiveness pruning — remove rules that didn't reduce friction
$ruleTrackFile = "$env:USERPROFILE\.claude\.claude\rule_effectiveness.json"
if (Test-Path $ruleTrackFile) {
    try {
        $ruleTrack = Get-Content $ruleTrackFile -Raw | ConvertFrom-Json
        $currentFriction = 0
        if (Test-Path $frictionDir) {
            Get-ChildItem $frictionDir -File -Filter "events.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
                $currentFriction += (Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue | Where-Object { $_ }).Count
            }
        }

        $toRemove = @()
        foreach ($rid in $ruleTrack.PSObject.Properties.Name) {
            $rt = $ruleTrack.{$rid}
            if ($rt.status -ne "active") { continue }
            $age = ($now - [datetime]$rt.added).TotalDays
            if ($age -lt 7) { continue }  # Give rules at least 7 days

            # If friction hasn't decreased, mark as ineffective
            if ($currentFriction -ge [int]$rt.friction_before) {
                $rt.status = "ineffective"
                $toRemove += $rt.rule
            } elseif ($currentFriction -lt [int]$rt.friction_before) {
                $rt.status = "effective"
                $changes += "L5e: rule '$($rt.rule)' effective (friction $($rt.friction_before) → $currentFriction)"
            }
        }

        # Prune ineffective rules from CLAUDE.md
        if ($toRemove.Count -gt 0) {
            $claudeContent = Get-Content $claudeMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            foreach ($rule in $toRemove) {
                $claudeContent = $claudeContent -replace [regex]::Escape("- $rule`n"), ""
                $claudeContent = $claudeContent -replace [regex]::Escape("- $rule"), ""
            }
            Set-Content $claudeMd -Value $claudeContent -Encoding UTF8 -NoNewline
            $applied += "L5e: pruned $($toRemove.Count) ineffective rule(s) from CLAUDE.md: $($toRemove -join ', ')"
        }
        $ruleTrack | ConvertTo-Json | Set-Content $ruleTrackFile -Encoding UTF8
    } catch {}
}

# 5f: Auto-delete confirmed-unused scripts (>30 days untouched)
$unused | ForEach-Object {
    $scriptPath = Join-Path "$env:USERPROFILE\.claude\scripts\hooks" $_
    if (Test-Path $scriptPath) {
        $age = ((Get-Date) - (Get-Item $scriptPath).LastWriteTime).TotalDays
        if ($age -gt 30) {
            Remove-Item $scriptPath -Force -ErrorAction SilentlyContinue
            $applied += "L5d: auto-deleted '$_' (unused for $([int]$age) days)"
        }
    }
}

# ═══════════════════════════════════════
# MEMORY DISTILLATION (L4)
# ═══════════════════════════════════════
if (Test-Path $memDir) {
    $memIndex = Join-Path $memDir "MEMORY.md"
    if (Test-Path $memIndex) {
        $memContent = Get-Content $memIndex -Raw -Encoding UTF8

        # Count memories by tag — only on memory entries (skip legend lines)
        $entryLines = ($memContent -split "`n" | Where-Object { $_ -match '^- \[' })
        $entryContent = $entryLines -join "`n"
        $freshCount = ([regex]::Matches($entryContent, '\[fresh\]')).Count
        $agingCount = ([regex]::Matches($entryContent, '\[aging\]')).Count
        $staleCount = ([regex]::Matches($entryContent, '\[stale\]')).Count
        $expiredCount = ([regex]::Matches($entryContent, '\[expired\]')).Count

        if ($expiredCount -gt 0) {
            $changes += "L4: $expiredCount 条记忆已过期，建议清理"
        }
        if ($staleCount -gt 3) {
            $changes += "L4: $staleCount 条记忆将过期，建议蒸馏"
        }
    }
}

# ═══════════════════════════════════════
# EVOLUTION VERIFICATION + AUTO-ROLLBACK
# ═══════════════════════════════════════
if ($applied.Count -gt 0) {
    $verifyOk = $true
    $verifyErrors = @()

    # 1. settings.json must be valid JSON
    try { Get-Content $settingsJson -Raw | ConvertFrom-Json | Out-Null } catch {
        $verifyOk = $false; $verifyErrors += "settings.json invalid: $_"
    }

    # 2. All hook scripts must parse clean
    Get-ChildItem "$env:USERPROFILE\.claude\scripts\hooks\*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
        $nullVar = $null; $pe = @()
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$nullVar, [ref]$pe)
        if ($pe.Count -gt 0) { $verifyOk = $false; $verifyErrors += "$($_.Name): $($pe.Count) parse errors" }
    }

    # 3. Every hook reference must point to existing script
    try {
        $currentSettings = Get-Content $settingsJson -Raw | ConvertFrom-Json
        foreach ($eventName in $currentSettings.hooks.PSObject.Properties.Name) {
            foreach ($group in $currentSettings.hooks.$eventName) {
                foreach ($h in $group.hooks) {
                    if ($h.command -match '([^\\"]+\.ps1)') {
                        if (-not (Test-Path (Join-Path "$env:USERPROFILE\.claude\scripts\hooks" $Matches[1]))) {
                            $verifyOk = $false; $verifyErrors += "$eventName → $($Matches[1]) not found"
                        }
                    }
                }
            }
        }
    } catch { $verifyOk = $false; $verifyErrors += "Cannot parse settings.json for hook verification" }

    if (-not $verifyOk) {
        # AUTO-ROLLBACK: git revert to pre-evolution snapshot
        $rollbackMsg = "ROLLBACK: verification failed — $($verifyErrors -join '; ')"
        $changes += $rollbackMsg
        try {
            Push-Location "$env:USERPROFILE\.claude"
            $preCommit = & git log --oneline -1 --grep="pre-evolution" --format="%H" 2>$null
            if ($preCommit) {
                & git reset --hard $preCommit 2>$null
                $changes += "ROLLBACK: reverted to pre-evolution commit $($preCommit.Substring(0,8))"
            } else {
                # Fallback: revert last commit if it was an evolution
                $lastMsg = & git log --oneline -1 --format="%s" 2>$null
                if ($lastMsg -match 'evo:|post-evolution') {
                    & git reset --hard HEAD~1 2>$null
                    $changes += "ROLLBACK: reverted last evolution commit"
                }
            }
            Pop-Location
        } catch { $changes += "ROLLBACK FAILED: $_" }
        $applied = @()  # Clear applied changes since they were rolled back
    }
}

# ═══════════════════════════════════════
# LOG, GATE UPDATE, REPORT
# ═══════════════════════════════════════
$allChanges = @($applied) + @($changes)

# Log ALL observations, but only update gate for actual modifications
$event = @{ timestamp = (Get-Date -Format "o"); type = "evolution"; changes = $allChanges }
$event | ConvertTo-Json -Compress | Add-Content $evolveLog -Encoding UTF8

if ($applied.Count -gt 0) {
    # Update gate — only when real changes applied (not just L5 observations)
    $gateData = @{
        last_evolution = (Get-Date -Format "o")
        session_count_since_last = 0
        recent_evo_timestamps = @()
        rule_additions_this_cycle = 0
    }
    if (Test-Path $gateFile) {
        try {
            $existing = Get-Content $gateFile -Raw | ConvertFrom-Json
            $recentTs = @($existing.recent_evo_timestamps) + @((Get-Date -Format "o"))
            $gateData.recent_evo_timestamps = @($recentTs | Select-Object -Last 15)
            $l1Adds = ($applied | Where-Object { $_ -match "^L1:" }).Count
            $gateData.rule_additions_this_cycle = [int]$existing.rule_additions_this_cycle + $l1Adds
        } catch { }
    }
    $gateData | ConvertTo-Json | Set-Content $gateFile -Encoding UTF8

    # Post-evolution snapshot
    if (Test-Path $snapshotScript) {
        $changeSummary = ($allChanges -join "; ")
        if ($changeSummary.Length -gt 200) { $changeSummary = $changeSummary.Substring(0, 200) + "…" }
        & pwsh -ExecutionPolicy Bypass -File $snapshotScript -Message "evo: $changeSummary" 2>$null
    }

    $msg = ($allChanges | ForEach-Object { "  $_" }) -join "`n"
    Write-Output "EVOLVE:`n$msg"
}

# Cleanup: truncate large perf files
if (Test-Path $perfDir) {
    Get-ChildItem $perfDir -File -Filter "*.jsonl" -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -gt 500000 } |
        ForEach-Object {
            $keep = Get-Content $_.FullName -Tail 100 -Encoding UTF8
            $keep | Set-Content $_.FullName -Encoding UTF8
        }
}

exit 0
