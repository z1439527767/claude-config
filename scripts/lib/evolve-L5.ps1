# evolve-L5.ps1 — Proactive optimization (unused scripts, redundancy, error patterns, rule pruning)
# Sourced by evolve.ps1; appends to $script:applied and $script:changes
param()

$scriptsDir = "$env:USERPROFILE\.claude\scripts\hooks"
$claudeMd = "$env:USERPROFILE\.claude\CLAUDE.md"
$agentsMd = "$env:USERPROFILE\.claude\AGENTS.md"
$settingsJson = "$env:USERPROFILE\.claude\settings.json"
$evolveLog = "$env:USERPROFILE\.claude\.claude\evolution_log.jsonl"
$frictionDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"
$now = Get-Date

$settings = Get-Content $settingsJson -Raw | ConvertFrom-Json

# 5a: Detect unused scripts
$allScripts = @(Get-ChildItem "$scriptsDir\*.ps1" -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
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
foreach ($sn in $allScripts) {
    if ($referencedScripts[$sn]) { continue }
    $pat = [regex]::Escape($sn)
    foreach ($other in $allScripts) {
        if ($other -eq $sn) { continue }
        $otherContent = Get-Content (Join-Path $scriptsDir $other) -Raw -ErrorAction SilentlyContinue
        if ($otherContent -match "(?i)$pat") { $referencedScripts[$sn] = $true; break }
    }
}
$unused = $allScripts | Where-Object { -not $referencedScripts[$_] }
if ($unused.Count -gt 0) {
    $script:changes += "L5: $($unused.Count) unused scripts: $($unused -join ', ') — consider deleting"
}

# 5b: Detect rule redundancy
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
    if ($dupCount -gt 1) { $script:changes += "L5: $dupCount duplicate rules between CLAUDE.md and AGENTS.md" }
}

# 5c: Error pattern learning
$failureDir = "$env:USERPROFILE\.claude\.claude\tool_failures"
if (Test-Path $failureDir) {
    $recentChanges = @()
    if (Test-Path $evolveLog) {
        try {
            $lastLines = Get-Content $evolveLog -Tail 5 -Encoding UTF8 -ErrorAction SilentlyContinue
            foreach ($ll in $lastLines) {
                if ($ll) { try { $entry = $ll | ConvertFrom-Json; $recentChanges += @($entry.changes) } catch {} }
            }
        } catch {}
    }
    Get-ChildItem $failureDir -File -Filter "failures.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
        $failures = Get-Content $_.FullName -Tail 50 -ErrorAction SilentlyContinue |
            ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ }
        if ($failures.Count -lt 3) { return }
        $toolCounts = @{}
        foreach ($f in $failures) {
            if (-not $f.tool_name -or $f.tool_name -eq 'unknown' -or -not $f.tool_input) { continue }
            if (-not $toolCounts[$f.tool_name]) { $toolCounts[$f.tool_name] = 0 }
            $toolCounts[$f.tool_name]++
        }
        $hotTools = $toolCounts.GetEnumerator() | Where-Object { $_.Value -ge 3 } | Sort-Object Value -Descending
        foreach ($ht in $hotTools) {
            $obs = "L5: '$($ht.Name)' failed $($ht.Value) times — consider adding retry or fallback"
            if ($obs -notin $recentChanges) { $script:changes += $obs }
        }
    }
}

# 5d: Rule effectiveness pruning
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
            if ($age -lt 7) { continue }
            if ($currentFriction -ge [int]$rt.friction_before) {
                $rt.status = "ineffective"; $toRemove += $rt.rule
            } elseif ($currentFriction -lt [int]$rt.friction_before) {
                $rt.status = "effective"
                $script:changes += "L5e: rule '$($rt.rule)' effective (friction $($rt.friction_before) → $currentFriction)"
            }
        }
        if ($toRemove.Count -gt 0) {
            $claudeContent = Get-Content $claudeMd -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            foreach ($rule in $toRemove) {
                $claudeContent = $claudeContent -replace [regex]::Escape("- $rule`n"), ""
                $claudeContent = $claudeContent -replace [regex]::Escape("- $rule"), ""
            }
            # Atomic write: temp → rename
            $tmpMd = "$claudeMd.tmp.$([Guid]::NewGuid().ToString('N').Substring(0,8))"
            try {
                Set-Content $tmpMd -Value $claudeContent -Encoding UTF8 -NoNewline
                Move-Item -Force $tmpMd $claudeMd
                $script:applied += "L5e: pruned $($toRemove.Count) ineffective rule(s) from CLAUDE.md"
            } catch { if (Test-Path $tmpMd) { Remove-Item $tmpMd -Force -ErrorAction SilentlyContinue } }
        }
        # Atomic write state file
        $tmpRt = "$ruleTrackFile.tmp.$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        try { $ruleTrack | ConvertTo-Json | Set-Content $tmpRt -Encoding UTF8; Move-Item -Force $tmpRt $ruleTrackFile } catch { if (Test-Path $tmpRt) { Remove-Item $tmpRt -Force -ErrorAction SilentlyContinue } }
    } catch {}
}

# 5f: Auto-delete unused scripts >30 days
$unused | ForEach-Object {
    $scriptPath = Join-Path $scriptsDir $_
    if (Test-Path $scriptPath) {
        $age = ((Get-Date) - (Get-Item $scriptPath).LastWriteTime).TotalDays
        if ($age -gt 30) {
            Remove-Item $scriptPath -Force -ErrorAction SilentlyContinue
            $script:applied += "L5f: auto-deleted '$_' (unused for $([int]$age) days)"
        }
    }
}
