# evolve-verify.ps1 — Post-evolution verification + auto-rollback
# Sourced by evolve.ps1; uses $script:applied and $script:changes
param()

if ($script:applied.Count -eq 0) { return }

$settingsJson = "$env:USERPROFILE\.claude\settings.json"
$verifyOk = $true
$verifyErrors = @()

# 1. settings.json must be valid JSON
try { Get-Content $settingsJson -Raw | ConvertFrom-Json | Out-Null } catch {
    $verifyOk = $false; $verifyErrors += "settings.json invalid: $_"
}

# 2. All hook scripts must parse clean (suppress output to avoid noise)
$null = Get-ChildItem "$env:USERPROFILE\.claude\scripts\hooks\*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    $nullVar = $null; $pe = @()
    $null = [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$nullVar, [ref]$pe)
    if ($pe.Count -gt 0) { $verifyOk = $false; $verifyErrors += "$($_.Name): $($pe.Count) parse errors" }
}

# 3. Every hook reference must point to existing script
try {
    $currentSettings = Get-Content $settingsJson -Raw | ConvertFrom-Json
    foreach ($eventName in $currentSettings.hooks.PSObject.Properties.Name) {
        foreach ($group in $currentSettings.hooks.$eventName) {
            foreach ($h in $group.hooks) {
                if ($h.command -match '([^\\"]+\.ps1)') {
                    $spHook = Join-Path "$env:USERPROFILE\.claude\scripts\hooks" $Matches[1]
                    $spLib  = Join-Path "$env:USERPROFILE\.claude\scripts\lib" $Matches[1]
                    $spRoot = Join-Path "$env:USERPROFILE\.claude\scripts" $Matches[1]
                    if (-not (Test-Path $spHook) -and -not (Test-Path $spLib) -and -not (Test-Path $spRoot)) {
                        $verifyOk = $false; $verifyErrors += "$eventName → $($Matches[1]) not found"
                    }
                }
            }
        }
    }
} catch { $verifyOk = $false; $verifyErrors += "Cannot parse settings.json for hook verification" }

if (-not $verifyOk) {
    $rollbackMsg = "ROLLBACK: verification failed — $($verifyErrors -join '; ')"
    $script:changes += $rollbackMsg
    # Surgical restore from evo_backups — never git reset (destroys unrelated commits)
    $backupDir = "$env:USERPROFILE\.claude\.claude\evo_backups"
    $ts = (Get-Date -Format "yyyyMMdd_HHmmss")
    $restored = @()
    @("$env:USERPROFILE\.claude\settings.json", "$env:USERPROFILE\.claude\CLAUDE.md", "$env:USERPROFILE\.claude\AGENTS.md") | ForEach-Object {
        if (Test-Path $_) {
            $latest = Get-ChildItem $backupDir -File -Filter "$(Split-Path $_ -Leaf).*.bak" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($latest) {
                try {
                    Copy-Item $latest.FullName $_ -Force -ErrorAction Stop
                    $restored += Split-Path $_ -Leaf
                } catch {}
            }
        }
    }
    if ($restored.Count -gt 0) {
        $script:changes += "ROLLBACK: surgically restored $($restored -join ', ') from backup"
    } else {
        $script:changes += "ROLLBACK: no backup found, manual recovery needed"
    }
    $script:applied = @()
}
