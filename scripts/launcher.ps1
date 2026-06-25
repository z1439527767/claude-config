# Ralph Launcher v2 — Dual-mode: Self + Project
# C:\Users\z1439\.claude = Core agent (always loaded)
# Project path = User-chosen work directory (isolated)
# Both load: global rules + project rules coexist

param(
    [string]$ProjectPath = "",
    [switch]$Self = $false,
    [switch]$ListRecent = $false
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

# ═══ Config ═══
$CORE_PATH = "$env:USERPROFILE\.claude"
$RECENT_FILE = "$CORE_PATH\session-env\recent_projects.json"

# ═══ API Config ═══
$env:ANTHROPIC_BASE_URL            = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN          = "sk-b395615ed9424e178a1a1c9ef3499310"
$env:ANTHROPIC_MODEL               = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL   = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL  = "deepseek-v4-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL     = "deepseek-v4-flash"

# ═══ Helper Functions ═══

function Write-Banner {
    Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║  🧠 RALPH LOOP — Agent Launcher v2        ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Save-RecentProject {
    param([string]$Path)
    $recent = @()
    if (Test-Path $RECENT_FILE) {
        try { $recent = Get-Content $RECENT_FILE -Raw | ConvertFrom-Json } catch { $recent = @() }
    }
    # Deduplicate and prepend
    $recent = @($Path) + ($recent | Where-Object { $_ -ne $Path })
    $recent = $recent | Select-Object -First 10
    $recent | ConvertTo-Json | Set-Content $RECENT_FILE -Encoding UTF8
}

function Show-RecentProjects {
    if (Test-Path $RECENT_FILE) {
        try {
            $recent = Get-Content $RECENT_FILE -Raw | ConvertFrom-Json
            if ($recent.Count -gt 0) {
                Write-Host "  Recent projects:" -ForegroundColor DarkGray
                for ($i = 0; $i -lt $recent.Count; $i++) {
                    $marker = if ($i -eq 0) { "→" } else { " " }
                    $exists = if (Test-Path $recent[$i]) { "✓" } else { "✗" }
                    Write-Host "  $marker [$i] $exists $($recent[$i])" -ForegroundColor DarkGray
                }
                Write-Host ""
            }
        } catch {}
    }
}

function Show-CapabilitySummary {
    $toolCount = (Get-ChildItem "$CORE_PATH\scripts\*.py" -ErrorAction SilentlyContinue).Count
    $ruleCount = (Get-ChildItem "$CORE_PATH\.claude\rules\*.md" -ErrorAction SilentlyContinue).Count
    $agentCount = (Get-ChildItem "$CORE_PATH\.claude\agents\*.md" -ErrorAction SilentlyContinue).Count
    $hookCount = (Get-ChildItem "$CORE_PATH\scripts\hooks\*.ps1" -ErrorAction SilentlyContinue).Count

    Write-Host "  🛠️  Core Capabilities:" -ForegroundColor DarkGray
    Write-Host "     $toolCount tools | $ruleCount rules | $agentCount agents | $hookCount hooks" -ForegroundColor DarkGray
    Write-Host ""
}

# ═══ Main ═══

Write-Banner

# ── Determine Project Path ──

if ($ListRecent) {
    Show-RecentProjects
    exit 0
}

if ($Self) {
    # Self mode: work on the core agent itself
    $ProjectPath = $CORE_PATH
    Write-Host "  🔧 MODE: SELF — Working on Ralph's core system" -ForegroundColor Yellow
    Write-Host "  📂 Path: $ProjectPath" -ForegroundColor Yellow
} elseif ($ProjectPath -and (Test-Path $ProjectPath)) {
    # CLI arg provided and exists
    Write-Host "  📁 MODE: PROJECT — Working on user project" -ForegroundColor Green
    Write-Host "  📂 Path: $ProjectPath" -ForegroundColor Green
} elseif ($ProjectPath) {
    # CLI arg provided but doesn't exist — create?
    Write-Host "  ⚠️  Path does not exist: $ProjectPath" -ForegroundColor Red
    $create = Read-Host "  Create? [Y/n]"
    if ($create -ne 'n') {
        New-Item -ItemType Directory -Force $ProjectPath | Out-Null
        Write-Host "  ✅ Created: $ProjectPath" -ForegroundColor Green
    } else {
        $ProjectPath = ""
    }
}

# ── Interactive Selection (if no path yet) ──

if (-not $ProjectPath) {
    Show-RecentProjects
    Show-CapabilitySummary

    Write-Host "  Select project:" -ForegroundColor White
    Write-Host "    [number] — Recent project by index" -ForegroundColor DarkGray
    Write-Host "    [path]   — Absolute or relative path" -ForegroundColor DarkGray
    Write-Host "    [.]      — Current directory: $(Get-Location)" -ForegroundColor DarkGray
    Write-Host "    [self]   — Ralph's core system ($CORE_PATH)" -ForegroundColor DarkGray
    Write-Host "    [empty]  — Use current directory" -ForegroundColor DarkGray
    Write-Host ""

    $choice = Read-Host "  Project"

    if ($choice -eq 'self') {
        $ProjectPath = $CORE_PATH
        Write-Host "  🔧 SELF mode" -ForegroundColor Yellow
    } elseif ($choice -eq '.' -or $choice -eq '') {
        $ProjectPath = (Get-Location).Path
        Write-Host "  📁 Current directory: $ProjectPath" -ForegroundColor Green
    } elseif ($choice -match '^\d+$') {
        # Number = recent project index
        $recent = @()
        if (Test-Path $RECENT_FILE) {
            try { $recent = Get-Content $RECENT_FILE -Raw | ConvertFrom-Json } catch {}
        }
        $idx = [int]$choice
        if ($idx -lt $recent.Count -and (Test-Path $recent[$idx])) {
            $ProjectPath = $recent[$idx]
            Write-Host "  📁 Recent project: $ProjectPath" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Invalid index or path no longer exists" -ForegroundColor Red
            exit 1
        }
    } elseif (Test-Path $choice) {
        $ProjectPath = (Resolve-Path $choice).Path
        Write-Host "  📁 $ProjectPath" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Path not found: $choice" -ForegroundColor Red
        exit 1
    }
}

# ── Validate & Prepare ──

if (-not (Test-Path $ProjectPath)) {
    Write-Host "  ❌ Invalid path: $ProjectPath" -ForegroundColor Red
    exit 1
}

# Resolve to absolute
$ProjectPath = (Resolve-Path $ProjectPath).Path

# Check if it's a git repo — if so, go to root
try {
    $gitRoot = git -C $ProjectPath rev-parse --show-toplevel 2>$null
    if ($gitRoot) {
        $ProjectPath = $gitRoot
    }
} catch {}

# Save to recent
Save-RecentProject $ProjectPath

# ═══ Launch ═══

Write-Host ""
Write-Host "  ═══════════════════════════════════════" -ForegroundColor Cyan

$isSelf = ($ProjectPath -eq $CORE_PATH)
if ($isSelf) {
    Write-Host "  🧠 RALPH SELF MODE" -ForegroundColor Yellow
    Write-Host "  Working on agent core system" -ForegroundColor Yellow
} else {
    Write-Host "  📁 PROJECT MODE" -ForegroundColor Green

    # Check for project CLAUDE.md
    $projectClaudeMd = Join-Path $ProjectPath "CLAUDE.md"
    $projectAgentsMd = Join-Path $ProjectPath "AGENTS.md"
    $projectConventions = Join-Path $ProjectPath "CONVENTIONS.md"

    if (Test-Path $projectClaudeMd) {
        Write-Host "  📄 Project CLAUDE.md found" -ForegroundColor DarkGray
    } else {
        Write-Host "  💡 Tip: Create CLAUDE.md in project root for project-specific rules" -ForegroundColor DarkGray
    }
}

Write-Host "  📂 $ProjectPath" -ForegroundColor White
Write-Host "  ═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Navigate to project
Set-Location $ProjectPath

# Launch Claude Code
claude
