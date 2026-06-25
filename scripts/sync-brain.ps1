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
$memoryIndex = "$HomeDir/.claude/projects/C--Users-z1439--claude/memory/MEMORY.md"
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
        $mcpServers = $settings.mcpServers | Get-Member -MemberType NoteProperty -ErrorAction SilentlyContinue
        if (-not $mcpServers) {
            $issues += "[mcp-drift] No MCP servers in settings.json"
        }

        $hooks = $settings.hooks | Get-Member -MemberType NoteProperty -ErrorAction SilentlyContinue
        if (-not $hooks) {
            $issues += "[hook-drift] No hooks in settings.json"
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
        $issues += "[session-bloat] $($emptyDirs.Count) empty dirs in session-env/"
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

# ===== OUTPUT =====
if (-not $Quiet) {
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
