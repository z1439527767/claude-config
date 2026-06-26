# sync-brain.ps1 -- Cross-reference knowledge graph vs actual files/config
# Exit 0: clean, Exit 1: drift detected, Exit 2: error
param(
    [switch]$Quiet,
    [switch]$Fix
)

$ErrorActionPreference = "Stop"
$issues = @()
$fixed = @()

$HomeDir = $env:USERPROFILE
$rulesDir = "$HomeDir/.claude/.claude/rules"
$claudeMd = "$HomeDir/.claude/CLAUDE.md"
$settingsPath = "$HomeDir/.claude/settings.json"
# Detect memory dir dynamically (don't hardcode username)
$memoryIndex = Get-ChildItem "$HomeDir/.claude/projects" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "memory/MEMORY.md" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
if (-not $memoryIndex) { $memoryIndex = "$HomeDir/.claude/projects/C--Users-$env:USERNAME--claude/memory/MEMORY.md" }
$sessionEnv = "$HomeDir/.claude/session-env"

# ===== 1. CRITICAL FILES =====
$criticalFiles = @(
    @{Path="$HomeDir/.claude/CLAUDE.md"; Required=$true},
    @{Path="$HomeDir/.claude/AGENTS.md"; Required=$true},
    @{Path="$HomeDir/.claude/settings.json"; Required=$true},
    @{Path="$HomeDir/.claude/CLAUDE.local.md"; Required=$false}
)

foreach ($cf in $criticalFiles) {
    $exists = Test-Path $cf.Path -PathType Leaf
    if (-not $exists -and $cf.Required) {
        $issues += "[critical-missing] $($cf.Path)"
    }
}

# ===== 2. RULE ORPHANS =====
if (Test-Path $claudeMd) {
    $claudeContent = Get-Content $claudeMd -Raw
    $ruleFiles = Get-ChildItem $rulesDir -Filter "*.md" -ErrorAction SilentlyContinue

    foreach ($rf in $ruleFiles) {
        $rfName = $rf.Name
        $included = $claudeContent -match [regex]::Escape("@.claude/rules/$rfName")
        if (-not $included) {
            $ruleContent = Get-Content $rf.FullName -Raw
            $hasPathTrigger = $ruleContent -match '(?m)^paths:'
            $hasAlwaysMode = $ruleContent -match '(?m)^mode:\s*always'
            $hasProjectScope = $ruleContent -match 'project instructions'
            if (-not $hasPathTrigger -and -not $hasAlwaysMode -and -not $hasProjectScope) {
                $issues += "[orphan-rule] $rfName -- not @included, not path-triggered"
            }
        }
    }
}

# ===== 3. MCP & HOOKS CONSISTENCY =====
if (Test-Path $settingsPath) {
    try {
        $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json

        # Also discover plugin-based MCPs (Claude Code plugins carry their own .mcp.json)
        $pluginMcps = @()
        $pluginsDir = "$HomeDir/.claude/plugins/marketplaces"
        if (Test-Path $pluginsDir) {
            $pluginMcps = Get-ChildItem $pluginsDir -Recurse -Filter ".mcp.json" -ErrorAction SilentlyContinue |
                ForEach-Object {
                    try {
                        $pm = Get-Content $_.FullName -Raw | ConvertFrom-Json
                        $pm.mcpServers | Get-Member -MemberType NoteProperty -ErrorAction SilentlyContinue |
                            ForEach-Object { $_.Name }
                    } catch { }
                } | Sort-Object -Unique
        }

        $mcpServers = $settings.mcpServers | Get-Member -MemberType NoteProperty -ErrorAction SilentlyContinue
        if (-not $mcpServers -and -not $pluginMcps) {
            $issues += "[mcp-drift] No MCP servers in settings.json or plugins"
        } elseif (-not $mcpServers) {
            # Only plugin MCPs — this is fine (Claude Code plugin system)
            if (-not $Quiet) {
                Write-Output "[sync-brain] MCP: $($pluginMcps.Count) via plugins ($($pluginMcps -join ', '))"
            }
        } else {
            $mcpNames = $mcpServers | ForEach-Object { $_.Name }

            # Cross-check against npm global MCP packages
            $npmGlobal = "$env:APPDATA/npm"
            $npmMcps = Get-ChildItem "$npmGlobal" -Filter "*mcp*" -ErrorAction SilentlyContinue |
                ForEach-Object { $_.BaseName -replace '\.cmd$','' -replace '\.ps1$','' } |
                Sort-Object -Unique

            # MCP servers in settings.json but NOT in npm global
            $zombieMcps = $mcpNames | Where-Object { $_ -notin $npmMcps }
            if ($zombieMcps) {
                $issues += "[mcp-zombie] $($zombieMcps.Count) MCP in settings.json not in npm: $($zombieMcps -join ', ')"
            }

            # MCP servers in npm but NOT in settings.json (informational, not an error)
            $orphanMcps = $npmMcps | Where-Object { $_ -notin $mcpNames }
            if ($orphanMcps) {
                $fixed += "[mcp-external] $($orphanMcps.Count) MCP via npm/marketplace: $($orphanMcps -join ', ')"
            }

            # Flag project MCP in framework config
            $projectMcps = @('comfyui', 'comfyui-mcp')
            $leaked = $mcpNames | Where-Object { $_ -in $projectMcps }
            if ($leaked) {
                $issues += "[mcp-project-leak] Project MCP in framework settings.json: $($leaked -join ', ')"
            }
        }

        $hooks = $settings.hooks | Get-Member -MemberType NoteProperty -ErrorAction SilentlyContinue
        if (-not $hooks) {
            $issues += "[hook-drift] No hooks in settings.json"
        } else {
            # Verify every hook script referenced in settings.json exists
            $hookCount = 0; $missingScripts = @()
            foreach ($event in ($settings.hooks | Get-Member -MemberType NoteProperty)) {
                foreach ($entry in $settings.hooks.($event.Name)) {
                    foreach ($h in $entry.hooks) {
                        $hookCount++
                        # Match both scripts\hooks\X.ps1 and scripts\X.ps1 paths (dynamic username)
                        $escapedHome = [regex]::Escape("$env:USERNAME\.claude\scripts\")
                        if ($h.command -match ($escapedHome + '(?:hooks\\)?([^" ]+\.ps1)')) {
                            $fname = $Matches[1]
                            $spHook = "$HomeDir/.claude/scripts/hooks/$fname"
                            $spRoot = "$HomeDir/.claude/scripts/$fname"
                            if (-not (Test-Path $spHook) -and -not (Test-Path $spRoot)) {
                                $missingScripts += $fname
                            }
                        }
                    }
                }
            }
            if ($missingScripts) {
                $issues += "[hook-missing] $($missingScripts.Count) hook scripts referenced but missing: $($missingScripts -join ', ')"
            }
        }
    } catch {
        $issues += "[settings-parse] Failed to parse settings.json: $_"
    }
}

# ===== 4. MEMORY INDEX COUNT =====
if (Test-Path $memoryIndex) {
    $indexContent = Get-Content $memoryIndex -Raw

    $indexEntries = 0
    $lineMatches = [regex]::Matches($indexContent, '^- \[', 'Multiline')
    if ($lineMatches) { $indexEntries = $lineMatches.Count }

    $memoryDir = Split-Path $memoryIndex -Parent
    $actualFiles = Get-ChildItem $memoryDir -Recurse -Filter "*.md" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "MEMORY.md" }
    $actualCount = @($actualFiles).Count

    if ($indexEntries -ne $actualCount) {
        $issues += "[memory-drift] MEMORY.md indexes $indexEntries entries, $actualCount .md files on disk"
    }
}

# ===== 5. SESSION-ENV BLOAT =====
if (Test-Path $sessionEnv) {
    $emptyDirs = Get-ChildItem $sessionEnv -Directory -ErrorAction SilentlyContinue | Where-Object {
        $childFiles = @(Get-ChildItem $_.FullName -File -ErrorAction SilentlyContinue)
        $childFiles.Count -eq 0
    }
    if ($emptyDirs -and $emptyDirs.Count -gt 0) {
        # Track recurring empty dirs: known harness dirs = silent cleanup, new ones = flag
        $knownFile = "$env:USERPROFILE\.claude\.claude\known_empty_dirs.json"
        $known = @{}
        if (Test-Path $knownFile) { try { $psObj = Get-Content $knownFile -Raw | ConvertFrom-Json; $known = @{}; foreach ($p in $psObj.PSObject.Properties) { $known[$p.Name] = [int]$p.Value } } catch {} }
        $newDirs = @()
        foreach ($d in $emptyDirs) {
            if (-not $known[$d.Name]) { $newDirs += $d; $known[$d.Name] = 1 }
            else { $known[$d.Name] += 1 }
        }
        $tmpKnown = "$knownFile.tmp.$([Guid]::NewGuid().ToString("N").Substring(0,8))"
        try { $known | ConvertTo-Json | Set-Content $tmpKnown -Encoding UTF8; Move-Item -Force $tmpKnown $knownFile } catch {}
        if ($newDirs.Count -gt 0) {
            $issues += "[session-bloat] $($newDirs.Count) new empty dirs: $($newDirs.Name -join ", ")"
        }
    }
}

# ===== 6. GIT REPO STATE =====
$gitDir = "$HomeDir/.claude/.git"
if (Test-Path $gitDir) {
    $dirty = $false
    try {
        $status = git -C "$HomeDir/.claude" status --porcelain 2>$null
        if ($status) { $dirty = $true }
    } catch { }

    $ahead = $false
    try {
        $aheadCount = git -C "$HomeDir/.claude" rev-list --count '@{u}..HEAD' 2>$null
        if ($aheadCount -and [int]$aheadCount -gt 0) { $ahead = $true }
    } catch { }

    if ($dirty) {
        $issues += "[git-dirty] Uncommitted changes in .claude repo"
    }
    if ($ahead) {
        $issues += "[git-ahead] $aheadCount commits ahead of origin"
    }
}

# ===== AUTO-FIX (when -Fix is specified) =====
if ($Fix -and $issues.Count -gt 0) {
    # Fix: session-bloat → remove empty dirs
    if ((Test-Path $sessionEnv) -and ($issues -match 'session-bloat')) {
        Get-ChildItem $sessionEnv -Directory -ErrorAction SilentlyContinue | Where-Object {
            @(Get-ChildItem $_.FullName -File -ErrorAction SilentlyContinue).Count -eq 0
        } | ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            # Feed KG signal (auto-fixed)
    . "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
    Write-KgSignal -Source "sync-brain" -EntityName "fix-$((Get-Date).ToString('yyyyMMdd'))" -EntityType "auto-fix" -Observations @($issue) -Priority "normal"
        $fixed += "[auto-fix] removed empty session dir: $($_.Name)"
        }
        $issues = $issues | Where-Object { $_ -notmatch 'session-bloat' }
    }

    # Fix: git-dirty → auto-commit if running in loop context
    if (($issues -match 'git-dirty') -and (Test-Path "$HomeDir/.claude/.git")) {
        $status = git -C "$HomeDir/.claude" status --porcelain 2>$null
        if ($status) {
            git -C "$HomeDir/.claude" add -A 2>$null
            $msg = $status -join '; '
            git -C "$HomeDir/.claude" commit -m "auto: sync-brain fix — $msg" 2>$null
            # Feed KG signal (auto-fixed)
    . "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
    Write-KgSignal -Source "sync-brain" -EntityName "fix-$((Get-Date).ToString('yyyyMMdd'))" -EntityType "auto-fix" -Observations @($issue) -Priority "normal"
        $fixed += "[auto-fix] committed dirty files"
            $issues = $issues | Where-Object { $_ -notmatch 'git-dirty' }
        }
    }
}

# ===== 7. PATTERN DETECTION (passive rules → active checks) =====
$patternResult = & "$HomeDir/.claude/scripts/pattern-detector.ps1" -Quiet
if ($LASTEXITCODE -ne 0) {
    # pattern-detector found issues — they're already logged to kg_signals.jsonl
    # Just note it for sync-brain visibility
    $patternIssues = @($patternResult | Where-Object { $_ -match '^\s*!' })
    if ($patternIssues.Count -gt 0) {
        $issues += "[pattern-signal] $($patternIssues.Count) passive→active pattern(s) detected"
    }
}

# ===== 8. SELF-AUDIT COMPLIANCE =====
$auditStateFile = "$HomeDir/.claude/.claude/audit_state.json"
if (Test-Path $auditStateFile) {
    try {
        $auditState = Get-Content $auditStateFile -Raw | ConvertFrom-Json
        $lastAudit = [DateTime]::Parse($auditState.last_audit)
        $elapsed = (Get-Date) - $lastAudit
        if ($elapsed.TotalHours -gt 1) {
            $issues += "[audit-overdue] Last self-audit was $([Math]::Round($elapsed.TotalHours,1))h ago (streak=$($auditState.streak))"
        }
    } catch {}
} else {
    $issues += "[audit-missing] No audit state file — self-audit never ran"
}

# ===== OUTPUT ====
if (-not $Quiet) {
    if ($fixed.Count -gt 0) {
        Write-Output "[sync-brain] FIXED: $($fixed.Count) issue(s)"
        foreach ($f in $fixed) { Write-Output "  ✓ $f" }
    }
    if ($issues.Count -eq 0) {
        Write-Output "[sync-brain] OK: brain and files are in sync"
    } else {
        Write-Output "[sync-brain] DRIFT: $($issues.Count) issue(s)"
        foreach ($i in $issues) {
            Write-Output "  X $i"
        }
    }
}

if ($issues.Count -gt 0) { exit 1 }
exit 0
