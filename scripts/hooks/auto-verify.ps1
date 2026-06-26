# auto-verify.ps1 — PostToolUse: validate + auto-heal changed files
param(
    [string]$tool_name = "",
    [string]$tool_input = ""
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$perfHookName = "auto-verify"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

if ($tool_name -notin @("Edit", "Write")) { exit 0 }

try {
    $input = $tool_input | ConvertFrom-Json
    $filePath = $input.file_path
} catch { exit 0 }

if (-not $filePath -or -not (Test-Path $filePath)) { exit 0 }

    # Stage 0: Integrity check (file exists, not empty, not truncated)
    $fileSize = (Get-Item $filePath).Length
    if ($fileSize -eq 0) { Write-Output "[escalate] ${filePath}: empty file (0 bytes)"; exit 2 }
    if ($tool_input) {
        try {
            $parsed = $tool_input | ConvertFrom-Json
            $provided = $parsed.content
            if ($provided -and $provided.Length -gt 100) {
                $actual = Get-Content $filePath -Raw -Encoding UTF8
                if ($actual -and $actual.Length -lt ($provided.Length * 0.5)) {
                    Write-Output "[escalate] ${filePath}: truncation ($($actual.Length) of $($provided.Length) chars)"
                    exit 2
                }
            }
        } catch {}
    }

$ext = [IO.Path]::GetExtension($filePath).ToLower()
$errors = @()

# ── Stage 1: Validate ──
switch ($ext) {
    ".ps1" {
        $parseErrors = $null
        $null = [Management.Automation.Language.Parser]::ParseFile($filePath, [ref]$null, [ref]$parseErrors)
        if ($parseErrors.Count -gt 0) {
            $errors += @{file=$filePath; type="ps1"; msg=$parseErrors[0].Message; canHeal=$false}
        }
    }
    ".py" {
        $err = python -m py_compile "$filePath" 2>&1
        if ($LASTEXITCODE -ne 0) {
            # Only heal encoding-related issues, not general syntax errors
            $isEncoding = $err -match "encoding.*declared|Non-UTF|Non-ASCII|coding.*cookie|NULL byte"
            $errors += @{file=$filePath; type="py"; msg=$err; canHeal=$isEncoding}
        }
    }
    ".json" {
        # Use forward slashes to avoid Python unicode escape issues on Windows
        # path passed as sys.argv for safety
        $err = python -c "import json, sys; json.load(open(sys.argv[1]))" "$filePath" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $isHealable = $err -match "trailing|comma|Expecting.*property|delimiter|Extra data"
            $errors += @{file=$filePath; type="json"; msg=$err; canHeal=$isHealable}
        }
    }
    { $_ -in ".yaml", ".yml" } {
        $err = python -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" "$filePath" 2>&1
        if ($LASTEXITCODE -ne 0) { $errors += @{file=$filePath; type="yaml"; msg=$err; canHeal=$false} }
    }
}

if ($errors.Count -eq 0) {
    Write-PerfLog 0; exit 0
}

# ── Escalation Chain: Retry → Investigate → Fix → Rollback → Escalate ──
# Ref: cc-recovery — 99% self-recovery with tiered response (retry 55% → investigate 27% → fix 14% → pivot 2% → escalate <1%)
$healed = @()
$rolledBack = @()
$escalated = @()

foreach ($e in $errors) {
    $backup = $null
    $fp = $e.file -replace '\\', '/'

    # Level 1: Retry — re-validate (catches transient parse failures)
    Start-Sleep -Milliseconds 100
    $retryOk = $false
    switch ($e.type) {
        "py" { python -m py_compile $e.file 2>&1 | Out-Null; $retryOk = ($LASTEXITCODE -eq 0) }
        "json" { python -c "import json, sys; json.load(open(sys.argv[1]))" $e.file 2>&1 | Out-Null; $retryOk = ($LASTEXITCODE -eq 0) }
    }
    if ($retryOk) { $healed += @{file=$e.file; level="retry"}; continue }

    # Level 2: Investigate — only proceed if healable pattern recognized
    if (-not $e.canHeal) { $escalated += $e; continue }
    $content = Get-Content $e.file -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $content) { $escalated += $e; continue }
    $backup = $content

    # Level 3: Fix — targeted repair
    $fixed = $false
    $newContent = $content

    if ($e.type -eq "py" -and $e.msg -match "encoding.*declared|Non-UTF|Non-ASCII|coding.*cookie|NULL byte") {
        if ($content -notmatch "# -\*- coding:") {
            $newContent = "# -*- coding: utf-8 -*-`n" + $content
            $fixed = $true
        }
    }
    if ($e.type -eq "json" -and $e.msg -match "trailing|comma|Expecting|delimiter|Extra data") {
        $newContent = $content -replace ',\s*\}', '}'
        $newContent = $newContent -replace ',\s*\]', ']'
        if ($newContent -ne $content) { $fixed = $true }
    }

    if (-not $fixed) { $escalated += $e; continue }

    # Level 3b: Apply + re-validate
    $fixOk = $false
    try {
        [IO.File]::WriteAllText($e.file, $newContent, [Text.UTF8Encoding]::new($false))
        switch ($e.type) {
            "py" { python -m py_compile $e.file 2>&1 | Out-Null; $fixOk = ($LASTEXITCODE -eq 0) }
            "json" { python -c "import json, sys; json.load(open(sys.argv[1]))" $e.file 2>&1 | Out-Null; $fixOk = ($LASTEXITCODE -eq 0) }
        }
    } catch { }

    if ($fixOk) { $healed += @{file=$e.file; level="fix"}; continue }

    # Level 4: Rollback — revert fix that made things worse
    if ($backup) {
        try { [IO.File]::WriteAllText($e.file, $backup, [Text.UTF8Encoding]::new($false)) } catch { }
        $rolledBack += @{file=$e.file; attempted=$true}
    }
    $escalated += $e
}

# ── Report ──
if ($healed.Count -gt 0) {
    $items = ($healed | ForEach-Object { "$(Split-Path $_.file -Leaf)(L$($_.level))" }) -join ", "
    Write-Output "[auto-heal] $items"
}
if ($rolledBack.Count -gt 0) {
    $items = ($rolledBack | ForEach-Object { Split-Path $_.file -Leaf }) -join ", "
    Write-Output "[rollback] fix reverted: $items"
}
$exitCode = 0
if ($escalated.Count -gt 0) {
    $msgs = ($escalated | ForEach-Object { "$(Split-Path $_.file -Leaf): $($_.msg)" }) -join "`n"
    Write-Output "[escalate] $msgs"
    $exitCode = 2
}

Write-PerfLog $exitCode; exit $exitCode
