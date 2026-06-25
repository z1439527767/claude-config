# adapter-config.ps1 — Safe settings.json read/write/validate
# Usage:
#   adapter-config.ps1 -Get path.to.key          → read a value
#   adapter-config.ps1 -Set path.to.key -Value X  → write a value
#   adapter-config.ps1 -List Hooks                → list hooks by event
#   adapter-config.ps1 -Validate                  → JSON schema check
#   adapter-config.ps1 -Backup                    → create timestamped backup
param(
    [string]$Get,
    [string]$Set,
    [string]$Value,
    [switch]$List,
    [string]$ListSection,
    [switch]$Validate,
    [switch]$Backup
)

$ErrorActionPreference = "Stop"
$configPath = "$env:USERPROFILE\.claude\settings.json"
$localPath = "$env:USERPROFILE\.claude\settings.local.json"
$backupDir = "$env:USERPROFILE\.claude\.claude\config_backups"

# Ensure backup dir
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Force $backupDir | Out-Null }

function Read-Config {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if (Test-Path $localPath) {
        $local = Get-Content $localPath -Raw | ConvertFrom-Json
        # Shallow merge: local overrides main
        foreach ($prop in $local.PSObject.Properties) {
            if ($config.$($prop.Name) -is [PSCustomObject] -and $prop.Value -is [PSCustomObject]) {
                foreach ($sub in $prop.Value.PSObject.Properties) {
                    $config.$($prop.Name) | Add-Member -Force -NotePropertyName $sub.Name -NotePropertyValue $sub.Value
                }
            } else {
                $config | Add-Member -Force -NotePropertyName $prop.Name -NotePropertyValue $prop.Value
            }
        }
    }
    return $config
}

function Backup-Config {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupPath = Join-Path $backupDir "settings_$ts.json"
    Copy-Item $configPath $backupPath
    Write-Output "Backup: $backupPath"
    # Keep last 20
    Get-ChildItem $backupDir -Filter "settings_*.json" | Sort-Object LastWriteTime -Desc | Select-Object -Skip 20 | Remove-Item -Force
}

# ── Backup ──
if ($Backup) {
    Backup-Config
    exit 0
}

# ── Validate ──
if ($Validate) {
    $errors = @()
    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
        if (-not $config.hooks) { $errors += "Missing 'hooks' key" }
        else {
            $validEvents = @("PreToolUse","PostToolUse","PostToolUseFailure","UserPromptSubmit","SessionStart","Stop","SessionEnd","SubagentStop","PreCompact","PostCompact","Notification","SubagentStart")
            foreach ($ev in $config.hooks.PSObject.Properties.Name) {
                if ($ev -notin $validEvents) { $errors += "Unknown hook event: $ev" }
                foreach ($g in $config.hooks.$ev) {
                    foreach ($h in $g.hooks) {
                        if ($h.command -match '\.ps1') {
                            $sp = Join-Path "$env:USERPROFILE\.claude\scripts\hooks" (Split-Path $h.command -Leaf)
                            if (-not (Test-Path $sp)) { $errors += "Hook missing: $($h.command)" }
                        }
                    }
                }
            }
        }
        if (-not $config.permissions) { $errors += "Missing 'permissions' key" }
    } catch {
        $errors += "Invalid JSON: $_"
    }
    if ($errors.Count -eq 0) { Write-Output "✅ settings.json valid"; exit 0 }
    else { Write-Output "❌ $($errors -join '; ')"; exit 1 }
}

# ── List ──
if ($List -or $ListSection) {
    $config = Read-Config
    $section = if ($ListSection) { $ListSection } else { "hooks" }
    if ($section -eq "hooks") {
        foreach ($ev in $config.hooks.PSObject.Properties.Name) {
            $count = 0; foreach ($g in $config.hooks.$ev) { $count += $g.hooks.Count }
            Write-Output "$ev`: $count hooks"
            foreach ($g in $config.hooks.$ev) {
                foreach ($h in $g.hooks) {
                    $timeout = if ($h.timeout) { " (${timeout}s)" } else { "" }
                    Write-Output "  $($h.command)$timeout"
                }
            }
        }
    } elseif ($section -eq "permissions") {
        Write-Output "Mode: $($config.permissions.defaultMode)"
        if ($config.permissions.allow) {
            foreach ($a in $config.permissions.allow) {
                Write-Output "  allow: $($a | ConvertTo-Json -Compress)"
            }
        }
    } else {
        $val = $config.$section
        if ($val) { Write-Output ($val | ConvertTo-Json -Depth 5) }
    }
    exit 0
}

# ── Get ──
if ($Get) {
    $config = Read-Config
    $current = $config
    foreach ($part in $Get.Split('.')) {
        if ($current.PSObject.Properties.Name -contains $part) {
            $current = $current.$part
        } else {
            Write-Output "null (path not found: $Get)"; exit 1
        }
    }
    if ($current -is [string]) { Write-Output $current }
    else { Write-Output ($current | ConvertTo-Json -Depth 5) }
    exit 0
}

# ── Set ──
if ($Set) {
    if (-not $Value) { Write-Output "ERROR: -Value required"; exit 1 }
    Backup-Config

    # Read raw JSON to preserve formatting
    $raw = Get-Content $configPath -Raw
    $config = $raw | ConvertFrom-Json

    # Navigate to parent, set leaf
    $parts = $Set.Split('.')
    $leaf = $parts[-1]
    $parent = $config
    for ($i = 0; $i -lt $parts.Count - 1; $i++) {
        if (-not $parent.PSObject.Properties.Name -contains $parts[$i]) {
            $parent | Add-Member -Force -NotePropertyName $parts[$i] -NotePropertyValue (@{})
        }
        $parent = $parent.$($parts[$i])
    }

    # Try to cast Value to appropriate type
    $typedValue = $Value
    if ($Value -eq "true") { $typedValue = $true }
    elseif ($Value -eq "false") { $typedValue = $false }
    elseif ($Value -match '^\d+$') { $typedValue = [int]$Value }
    elseif ($Value -match '^\d+\.\d+$') { $typedValue = [double]$Value }

    if ($parent.PSObject.Properties.Name -contains $leaf) {
        $parent.$leaf = $typedValue
    } else {
        $parent | Add-Member -Force -NotePropertyName $leaf -NotePropertyValue $typedValue
    }

    # Atomic write: write to temp, validate, then move
    $tmpPath = "$configPath.tmp"
    $config | ConvertTo-Json -Depth 10 | Set-Content $tmpPath -Encoding UTF8
    try {
        $null = Get-Content $tmpPath -Raw | ConvertFrom-Json
        Move-Item $tmpPath $configPath -Force
        Write-Output "✅ Set $Set = $Value"
    } catch {
        Remove-Item $tmpPath -Force -ErrorAction SilentlyContinue
        Write-Output "❌ Validation failed, not written: $_"; exit 1
    }
    exit 0
}

Write-Output "Usage: adapter-config.ps1 [-Get path] [-Set path -Value val] [-List] [-Validate] [-Backup]"
