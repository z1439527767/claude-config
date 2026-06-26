# ps-lint.ps1 — Anti-pattern detector for production-grade PowerShell
# PostToolUse hook: catches 7 anti-patterns before they reach commit
param(
    [string]$tool_name = "",
    [string]$tool_input = ""
)

$ErrorActionPreference = "Continue"
$perfHookName = "ps-lint"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

if ($tool_name -notin @("Edit", "Write")) { Write-PerfLog 0; exit 0 }

try { $input = $tool_input | ConvertFrom-Json; $filePath = $input.file_path } catch { Write-PerfLog 0; exit 0 }
if (-not $filePath -or $filePath -notmatch '\.ps1$') { Write-PerfLog 0; exit 0 }
if (-not (Test-Path $filePath)) { Write-PerfLog 0; exit 0 }

$content = Get-Content $filePath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
if (-not $content) { Write-PerfLog 0; exit 0 }

$issues = @()

# 1. Hardcoded python3
if ($content -match '\bpython3\b') {
    $issues += "[python3] Use 'python' not 'python3' (Windows compat)"
}

# 2. Hardcoded username/path
if ($content -match 'z1439|C--Users-z1439--claude') {
    $issues += "[hardcoded-user] Use `$env:USERNAME or dynamic detection"
}

# 3. Set-Content on critical files (not in perf cleanup)
$criticalPatterns = @('MEMORY\.md', 'settings\.json', '\.json"', "\.json'", 'evo_gate', 'distill_state', 'memory_scores')
$hasSetContent = $content -match '\bSet-Content\b'
$hasCriticalPath = ($criticalPatterns | Where-Object { $content -match $_ }).Count -gt 0
if ($hasSetContent -and $hasCriticalPath) {
    # Allow Set-Content in cleanup contexts (perf truncation, tmp files)
    if ($content -notmatch '\.tmp|hook_perf|Tail\s+\d+') {
        $issues += "[set-content] Use [IO.File]::WriteAllText for critical files (no BOM, no trailing newline)"
    }
}

# 4. Global SilentlyContinue
if ($content -match '^\$ErrorActionPreference\s*=\s*["'']SilentlyContinue') {
    $issues += "[silent-fail] Global SilentlyContinue swallows all errors"
}

# 5. Missing ErrorActionPreference
if ($content -notmatch '\$ErrorActionPreference\s*=') {
    $issues += "[no-eap] Missing explicit `$ErrorActionPreference at script top"
}

# 6. No $env:USERPROFILE validation before use
if ($content -match '\$env:USERPROFILE' -and $content -notmatch 'if\s*\(\s*-not\s*\$env:USERPROFILE|Test-Path\s+\$env:USERPROFILE') {
    # Not a hard error, but flag for scripts that heavily rely on it
}

# 7. Write-Host in hook scripts (hooks must use Write-Output)
if ($content -match '\bWrite-Host\b') {
    $issues += "[write-host] Hook scripts must use Write-Output, not Write-Host"
}

if ($issues.Count -gt 0) {
    $fname = Split-Path $filePath -Leaf
    Write-Output "[ps-lint] $($fname): $($issues -join '; ')"

    # Feed into evolution pipeline: write friction event so L1 can detect patterns
    $frictionDir = "$env:USERPROFILE\.claude\.claude\tellonce-state\friction"
    if (-not (Test-Path $frictionDir)) { try { New-Item -ItemType Directory -Force $frictionDir | Out-Null } catch {} }
    $event = @{
        timestamp = (Get-Date -Format "o")
        signals   = ($issues -join ", ")
        categories = "ps-lint"
        prompt_snippet = "ps-lint detected in $fname"
    } | ConvertTo-Json -Compress
    $logFile = Join-Path $frictionDir "events.jsonl"
    try { python "$env:USERPROFILE\.claude\scripts\adapter-db.py" insert "friction/events" "" $event 2>$null | Out-Null } catch {
        Add-Content -Path $logFile -Value $event -Encoding UTF8
    }

    Write-PerfLog 1; exit 1
}

Write-PerfLog 0; exit 0
