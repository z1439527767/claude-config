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
                    $spHook = Join-Path "$env:USERPROFILE\.claude\scripts\hooks" $Matches[1]
                    $spRoot = Join-Path "$env:USERPROFILE\.claude\scripts" $Matches[1]
                    if (-not (Test-Path $spHook) -and -not (Test-Path $spRoot)) {
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
    try {
        Push-Location "$env:USERPROFILE\.claude"
        $preCommit = & git log --oneline -1 --grep="pre-evolution" --format="%H" 2>$null
        if ($preCommit) {
            & git reset --hard $preCommit 2>$null
            $script:changes += "ROLLBACK: reverted to pre-evolution commit $($preCommit.Substring(0,8))"
        } else {
            $lastMsg = & git log --oneline -1 --format="%s" 2>$null
            if ($lastMsg -match 'evo:|post-evolution') {
                & git reset --hard HEAD~1 2>$null
                $script:changes += "ROLLBACK: reverted last evolution commit"
            }
        }
        Pop-Location
    } catch { $script:changes += "ROLLBACK FAILED: $_" }
    $script:applied = @()
}
