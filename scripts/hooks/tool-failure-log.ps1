# tool-failure-log.ps1 — PostToolUseFailure: log + pattern detection + recovery suggestions
param()
$ErrorActionPreference = "Continue"
$perfHookName = "tool-failure-log"; . "$env:USERPROFILE\.claude\scripts\lib\perf.ps1"

$logDir = "$env:USERPROFILE\.claude\.claude\tool_failures"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }

$toolName = $env:CLAUDE_TOOL_NAME
$toolInput = $env:CLAUDE_TOOL_INPUT
$errorMsg = $env:CLAUDE_TOOL_ERROR

# Skip PostToolUseFailure noise — harness fires this for internal operations
# where no tool metadata is available. Real failures always have either toolName or errorMsg.
if ((-not $toolName) -and (-not $errorMsg)) { _p 0; exit 0 }
if (-not $toolName) { $toolName = "unknown" }

# Log the failure
$entry = @{
    timestamp  = (Get-Date -Format "o")
    tool_name  = $toolName
    tool_input = if ($toolInput -and $toolInput.Length -gt 500) { $toolInput.Substring(0, 500) + "…" } else { $toolInput }
    error      = if ($errorMsg -and $errorMsg.Length -gt 1000) { $errorMsg.Substring(0, 1000) + "…" } else { $errorMsg }
} | ConvertTo-Json -Compress

Add-Content "$logDir\failures.jsonl" -Value $entry -Encoding UTF8

# Keep last 100 entries
$lines = @(Get-Content "$logDir\failures.jsonl" -Encoding UTF8 -ErrorAction SilentlyContinue)
if ($lines.Count -gt 100) { $lines[-100..-1] | Set-Content "$logDir\failures.jsonl" -Encoding UTF8 }

# ── Pattern detection: check for recurring failures ──
$allFailures = @($lines | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ })
$recentFailures = $allFailures | Where-Object {
    $_.timestamp -and ([datetime]$_.timestamp) -gt (Get-Date).AddHours(-24)
}

if ($recentFailures.Count -ge 3) {
    # Count failures by tool
    $toolFailCounts = @{}
    foreach ($f in $recentFailures) { if (-not $toolFailCounts[$f.tool_name]) { $toolFailCounts[$f.tool_name] = 0 }; $toolFailCounts[$f.tool_name]++ }

    # Write recovery suggestions
    $recFile = "$env:USERPROFILE\.claude\.claude\recovery_suggestions.json"
    $recs = @()
    foreach ($tool in $toolFailCounts.Keys) {
        $count = $toolFailCounts[$tool]
        if ($count -ge 3) {
            $suggestion = switch ($tool) {
                "Write" { "Write 工具频繁失败 — 先 Read 确认文件可写，检查路径是否存在" }
                "Edit"  { "Edit 工具频繁失败 — 检查 old_string 是否精确匹配，文件是否被外部修改" }
                "Bash"  { "Bash 频繁失败 — 检查命令是否在 PATH 上，语法是否正确" }
                "Read"  { "Read 工具频繁失败 — 检查文件路径是否存在，编码是否正确" }
                "PowerShell" { "PowerShell 频繁失败 — 检查 cmdlet 兼容性，使用 try/catch 包裹" }
                default { "$tool 连续失败 $count 次 — 建议检查工具参数和权限" }
            }
            $recs += @{ tool = $tool; failures = $count; suggestion = $suggestion }
        }
    }

    if ($recs.Count -gt 0) {
        $recs | ConvertTo-Json | Set-Content $recFile -Encoding UTF8
        Write-Output "RECOVERY: $($recs.Count) suggestion(s) written to recovery_suggestions.json"
    }
}

_p 0; exit 0
