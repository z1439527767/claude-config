# Ralph Launcher v3 — Two Worlds, One Portal
# 🧠 SELF  → C:\Users\z1439\.claude  (Ralph's brain — rules, tools, memory)
# 📁 PROJECT → your chosen directory  (your code — isolated from core)
# Core capabilities ALWAYS available in both modes.

param(
    [string]$Path = "",
    [switch]$Self,
    [switch]$List
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

# ═══ Config ═══
$CORE_PATH    = "$env:USERPROFILE\.claude"
$RECENT_FILE  = "$CORE_PATH\session-env\recent_projects.json"
$LAUNCHER_LOG = "$CORE_PATH\.claude\launcher_log.json"

# ═══ API ═══
$env:ANTHROPIC_API_KEY             = ""
$env:ANTHROPIC_BASE_URL            = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN          = if ($env:DEEPSEEK_API_KEY) { $env:DEEPSEEK_API_KEY } else { throw "DEEPSEEK_API_KEY not set. Run: `$env:DEEPSEEK_API_KEY='your-key'" }
$env:ANTHROPIC_MODEL               = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL   = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL  = "deepseek-v4-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL     = "deepseek-v4-flash"

# ═══ State ═══
function Load-State {
    if (Test-Path $LAUNCHER_LOG) {
        try { return Get-Content $LAUNCHER_LOG -Raw | ConvertFrom-Json }
        catch { return @{ last_mode = ""; launch_count = 0 } }
    }
    return @{ last_mode = ""; launch_count = 0 }
}
function Save-State($s) {
    $s | ConvertTo-Json | Set-Content $LAUNCHER_LOG -Encoding UTF8
}

# ═══ Recent Projects ═══
function Get-Recent {
    if (-not (Test-Path $RECENT_FILE)) { return @() }
    try {
        $all = Get-Content $RECENT_FILE -Raw | ConvertFrom-Json
        return @($all | Where-Object { Test-Path $_ })
    } catch { return @() }
}
function Add-Recent($p) {
    $recent = @($p) + (Get-Recent | Where-Object { $_ -ne $p })
    $recent | Select-Object -First 12 | ConvertTo-Json | Set-Content $RECENT_FILE -Encoding UTF8
}

# ═══ Core Stats ═══
function Get-CoreStats {
    $tools  = (Get-ChildItem "$CORE_PATH\scripts\*.py" -EA SilentlyContinue).Count
    $rules  = (Get-ChildItem "$CORE_PATH\.claude\rules\*.md" -EA SilentlyContinue).Count
    $hooks  = (Get-ChildItem "$CORE_PATH\scripts\hooks\*.ps1" -EA SilentlyContinue).Count
    $memory = 0
    $memIdx = "$CORE_PATH\projects\C--Users-z1439--claude\memory\MEMORY.md"
    if (Test-Path $memIdx) {
        $mc = Get-Content $memIdx -Raw -Encoding UTF8
        $memory = ($mc | Select-String '- \[').Matches.Count
    }
    return @{ tools = $tools; rules = $rules; hooks = $hooks; memory = $memory }
}

# ═══ Initialize New Project ═══
function New-Project($Path, $Name) {
    if (-not $Name) { $Name = Split-Path $Path -Leaf }
    Write-Host "`n  🏗️  Initializing: $Name" -ForegroundColor Cyan

    $isGit = try { git -C $Path rev-parse --show-toplevel 2>$null; $LASTEXITCODE -eq 0 } catch { $false }
    if (-not $isGit) { git -C $Path init 2>$null | Out-Null; Write-Host "     ✓ git init" -ForegroundColor DarkGray }

    $gi = Join-Path $Path ".gitignore"
    if (-not (Test-Path $gi)) {
        @"
node_modules/__pycache__/*.pyc
.venv/venv/.vscode/.idea/
Thumbs.db.DS_Store
.env*.pem
"@ | Set-Content $gi -Encoding UTF8
        Write-Host "     ✓ .gitignore" -ForegroundColor DarkGray
    }

    $cm = Join-Path $Path "CLAUDE.md"
    if (-not (Test-Path $cm)) {
        @"
# $Name

## Tech Stack
-

## Commands
-

## Code Style
-

## Notes
- Ralph tools available: verify-all, data-pack, cross-review, orchestrator
"@ | Set-Content $cm -Encoding UTF8
        Write-Host "     ✓ CLAUDE.md" -ForegroundColor DarkGray
    }

    $cv = Join-Path $Path "CONVENTIONS.md"
    if (-not (Test-Path $cv)) {
        Copy-Item "$CORE_PATH\CONVENTIONS.md" $cv -EA SilentlyContinue
        if (Test-Path $cv) { Write-Host "     ✓ CONVENTIONS.md" -ForegroundColor DarkGray }
    }

    Write-Host "  ✅ Ready`n" -ForegroundColor Green
}

# ═══════════════════════════════════════════
# RENDER
# ═══════════════════════════════════════════

function Show-Header {
    Clear-Host
    $stats = Get-CoreStats
    $state  = Load-State
    $state.launch_count = [int]$state.launch_count + 1
    Save-State $state

    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║        🧠  RALPH  LOOP  —  Launch  Portal     ║" -ForegroundColor Cyan
    Write-Host "  ╠══════════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "  ║  Core: $($stats.tools) tools | $($stats.rules) rules | $($stats.hooks) hooks | $($stats.memory) memories  ║" -ForegroundColor DarkGray
    Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Recent {
    $recent = Get-Recent
    if ($recent.Count -gt 0) {
        Write-Host "  📂 Recent projects:" -ForegroundColor DarkGray
        for ($i = 0; $i -lt [Math]::Min($recent.Count, 8); $i++) {
            $marker = if ($i -eq 0) { "→" } else { " " }
            $name   = Split-Path $recent[$i] -Leaf
            $parent = Split-Path $recent[$i] -Parent
            $parentShort = if ($parent.Length -gt 35) { "..." + $parent.Substring($parent.Length - 32) } else { $parent }
            Write-Host "     [$i]  $name" -ForegroundColor White -NoNewline
            Write-Host "  ← $parentShort" -ForegroundColor DarkGray
        }
        Write-Host ""
    }
}

function Show-ModeChoice {
    Write-Host "  ┌─────────────────────────────┬─────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │                             │                             │" -ForegroundColor DarkGray
    Write-Host "  │   " -ForegroundColor DarkGray -NoNewline
    Write-Host "🧠  SELF" -ForegroundColor Yellow -NoNewline
    Write-Host "                    │   " -ForegroundColor DarkGray -NoNewline
    Write-Host "📁  PROJECT" -ForegroundColor Green -NoNewline
    Write-Host "                │" -ForegroundColor DarkGray
    Write-Host "  │                             │                             │" -ForegroundColor DarkGray
    Write-Host "  │  Ralph's brain              │  Your code                  │" -ForegroundColor DarkGray
    Write-Host "  │  Rules · Tools · Memory     │  Isolated · Clean · Fast    │" -ForegroundColor DarkGray
    Write-Host "  │  $CORE_PATH" -ForegroundColor DarkGray -NoNewline
    Write-Host "│  Any project you choose      │" -ForegroundColor DarkGray
    Write-Host "  │                             │                             │" -ForegroundColor DarkGray
    Write-Host "  └─────────────────────────────┴─────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""
}

# ═══════════════════════════════════════════
# MODE: SELF
# ═══════════════════════════════════════════

function Invoke-SelfMode {
    Write-Host "  🧠 SELF MODE — Entering Ralph's Brain" -ForegroundColor Yellow
    Write-Host "  📂 $CORE_PATH" -ForegroundColor Yellow
    Write-Host ""

    Add-Recent $CORE_PATH
    Set-Location $CORE_PATH
    claude
}

# ═══════════════════════════════════════════
# MODE: PROJECT
# ═══════════════════════════════════════════

function Invoke-ProjectMode {
    param([string]$ProjectPath)
    Write-Host "  📁 PROJECT MODE" -ForegroundColor Green

    $projClaudeMd = Join-Path $ProjectPath "CLAUDE.md"
    if (Test-Path $projClaudeMd) { Write-Host "  📄 CLAUDE.md found" -ForegroundColor DarkGray }
    Write-Host "  📂 $ProjectPath" -ForegroundColor Green
    Write-Host ""

    if ($ProjectPath -ne $CORE_PATH) { Add-Recent $ProjectPath }
    Set-Location $ProjectPath
    claude
}

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

# Fast paths: CLI shortcuts
if ($List) { Show-Header; Show-Recent; exit 0 }

if ($Self) {
    Show-Header
    Invoke-SelfMode
    exit 0
}

if ($Path) {
    Show-Header
    if (Test-Path $Path) {
        $resolved = (Resolve-Path $Path).Path
        try { $gitRoot = git -C $resolved rev-parse --show-toplevel 2>$null; if ($gitRoot) { $resolved = $gitRoot } } catch {}
        Invoke-ProjectMode $resolved
    } else {
        Write-Host "  🆕 New project: $Path" -ForegroundColor Yellow
        $create = Read-Host "  Create? [Y/n]"
        if ($create -eq 'n') { exit 0 }
        New-Item -ItemType Directory -Force $Path | Out-Null
        $resolved = (Resolve-Path $Path).Path
        New-Project $resolved
        Invoke-ProjectMode $resolved
    }
    exit 0
}

# ── Interactive Mode ──
Show-Header
Show-ModeChoice

# Read last mode for hint
$state = Load-State
$lastHint = if ($state.last_mode) { " [last: $($state.last_mode)]" } else { "" }

$mode = Read-Host "  Enter mode${lastHint}: [self] or [project]"

if ($mode -eq 'self' -or $mode -eq 's') {
    $state.last_mode = "self"; Save-State $state
    Invoke-SelfMode
    exit 0
}

if ($mode -eq 'project' -or $mode -eq 'p' -or $mode -eq '') {
    $state.last_mode = "project"; Save-State $state

    Clear-Host
    Show-Header
    Show-Recent

    $recent = Get-Recent
    Write-Host "  ── Project Selection ──" -ForegroundColor White
    Write-Host "    [0-7]  Pick recent project" -ForegroundColor DarkGray
    Write-Host "    [path]  Existing or new project directory" -ForegroundColor DarkGray
    Write-Host "    [.]     Current directory: $(Get-Location)" -ForegroundColor DarkGray
    Write-Host "    [back]  Return to mode selection" -ForegroundColor DarkGray
    Write-Host ""

    $choice = Read-Host "  Project"

    if ($choice -eq 'back' -or $choice -eq 'b') {
        # Recurse: restart interactive
        & $PSCommandPath
        exit 0
    }

    if ($choice -eq '.' -or $choice -eq '') {
        $target = (Get-Location).Path
        try { $gitRoot = git -C $target rev-parse --show-toplevel 2>$null; if ($gitRoot) { $target = $gitRoot } } catch {}
        Invoke-ProjectMode $target
        exit 0
    }

    if ($choice -match '^\d+$') {
        $idx = [int]$choice
        if ($idx -lt $recent.Count) {
            Invoke-ProjectMode $recent[$idx]
            exit 0
        }
        Write-Host "  ❌ Invalid index" -ForegroundColor Red
        exit 1
    }

    if (Test-Path $choice) {
        $target = (Resolve-Path $choice).Path
        try { $gitRoot = git -C $target rev-parse --show-toplevel 2>$null; if ($gitRoot) { $target = $gitRoot } } catch {}
        Invoke-ProjectMode $target
        exit 0
    }

    # Doesn't exist — offer to create
    Write-Host "  🆕 New project: $choice" -ForegroundColor Yellow
    $create = Read-Host "  Create & initialize? [Y/n]"
    if ($create -eq 'n') { exit 0 }
    New-Item -ItemType Directory -Force $choice | Out-Null
    $target = (Resolve-Path $choice).Path
    New-Project $target
    Invoke-ProjectMode $target
    exit 0
}

Write-Host "  ❌ Invalid mode. Use: self / project" -ForegroundColor Red
exit 1
