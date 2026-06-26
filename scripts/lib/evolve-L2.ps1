# evolve-L2.ps1 — Success patterns → AGENTS.md principles
# Sourced by evolve.ps1; appends to $script:applied and $script:changes
param()

$agentsMd = "$env:USERPROFILE\.claude\AGENTS.md"
$claudeMd = "$env:USERPROFILE\.claude\CLAUDE.md"
$successFile = "$env:USERPROFILE\.claude\.claude\last_session_success.json"

if (-not (Test-Path $successFile)) { return }

try {
    $success = Get-Content $successFile -Raw | ConvertFrom-Json
    $patternFile = "$env:USERPROFILE\.claude\.claude\success_patterns.json"
    $patterns = @{}
    if (Test-Path $patternFile) { try { $patterns = Get-Content $patternFile -Raw | ConvertFrom-Json } catch {} }

    if ($success.achievements) {
        $ach = $success.achievements -join " "
        if ($ach -match "hook|脚本|script") { $patterns['hook-creation'] = [int]$patterns['hook-creation'] + 1 }
        if ($ach -match "fix|修复|bug") { $patterns['bug-fix'] = [int]$patterns['bug-fix'] + 1 }
        if ($ach -match "evolution|进化|evolve") { $patterns['evolution'] = [int]$patterns['evolution'] + 1 }
        if ($ach -match "clean|清理|删") { $patterns['cleanup'] = [int]$patterns['cleanup'] + 1 }
    }

    # Emit signal for LLM to synthesize (honest architecture: hook detects, LLM synthesizes)
    $signals = @()
    foreach ($pk in @('hook-creation','bug-fix','evolution','cleanup')) {
        if ([int]$patterns[$pk] -ge 3) {
            $signals += "L2_SIGNAL: $pk ($($patterns[$pk]) patterns) — distill into AGENTS.md principle"
            $patterns[$pk] = 0  # reset counter after signaling
        }
    }
    if ($signals.Count -gt 0) {
        $script:applied += ($signals -join ' | ')
    }

    # Atomic write for pattern state
    $tmpPf = "$patternFile.tmp.$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    try { $patterns | ConvertTo-Json | Set-Content $tmpPf -Encoding UTF8; Move-Item -Force $tmpPf $patternFile } catch { if (Test-Path $tmpPf) { Remove-Item $tmpPf -Force -ErrorAction SilentlyContinue } }

    $claudeLines = (Get-Content $claudeMd -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
    if ($claudeLines -gt 80) {
        $script:changes += "L2: CLAUDE.md $claudeLines 行 (>80), 建议清理旧规则"
    }
} catch {}
