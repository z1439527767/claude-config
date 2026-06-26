# auto-compact.ps1 — PostToolUse: monitor context pressure, trigger autonomous compact
# Runs after every tool use. When pressure > 85%, signals compact needed.
param()
$ErrorActionPreference = "Continue"

$baseDir = "$env:USERPROFILE\.claude"
$guardState = "$baseDir\.claude\context_guard_state.json"

# ── Multi-signal pressure estimation ──
# Signal 1: Static L0 load (CLAUDE.md + rules + memory)
$l0Tokens = 0
$claudeMd = "$baseDir\CLAUDE.md"
if (Test-Path $claudeMd) { $l0Tokens += [math]::Round((Get-Item $claudeMd).Length / 3) }
$rulesDir = "$baseDir\.claude\rules"
if (Test-Path $rulesDir) {
    Get-ChildItem $rulesDir -Filter "*.md" | ForEach-Object { $l0Tokens += [math]::Round($_.Length / 3) }
}
$memIndex = Get-ChildItem "$baseDir\projects" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "memory\MEMORY.md" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
if ($memIndex) { $l0Tokens += [math]::Round((Get-Item $memIndex).Length / 3) }

# Signal 2: Tool call count this session (proxy for conversation length)
$toolCountFile = "$baseDir\.claude\tool_count.txt"
$toolCount = 0
if (Test-Path $toolCountFile) {
    try { $toolCount = [int](Get-Content $toolCountFile -Raw) } catch { $toolCount = 0 }
}
$toolCount++
$toolCount | Set-Content $toolCountFile -Encoding UTF8

# Signal 3: Session duration
$sessionStartFile = "$baseDir\.claude\session_start_time.txt"
if (-not (Test-Path $sessionStartFile)) {
    (Get-Date -Format "o") | Set-Content $sessionStartFile -Encoding UTF8
}
$sessionStart = try { [datetime](Get-Content $sessionStartFile -Raw) } catch { Get-Date }
$sessionMinutes = [math]::Round(((Get-Date) - $sessionStart).TotalMinutes, 1)

# ── Heuristic Pressure Model ──
# Static files contribute at most 30% of budget
$staticRatio = [math]::Min(0.30, $l0Tokens / 200000)

# Each tool call adds ~500-2000 tokens of conversation. Estimate 1K per call.
$conversationTokens = $toolCount * 1000
$conversationRatio = [math]::Min(0.70, $conversationTokens / 200000)

# Combined pressure
$pressure = [math]::Min(1.0, $staticRatio + $conversationRatio)

# ── Save state ──
$state = @{
    last_check = (Get-Date -Format "o")
    static_tokens = $l0Tokens
    tool_count = $toolCount
    session_minutes = $sessionMinutes
    estimated_conversation = $conversationTokens
    pressure = [math]::Round($pressure, 2)
}
$state | ConvertTo-Json -Compress | Set-Content $guardState -Encoding UTF8

# ── Thresholds ──
$COMPACT_LINE = 0.85
$WARNING_LINE = 0.65

if ($pressure -ge $COMPACT_LINE) {
    $flagFile = "$baseDir\.claude\compact_needed.flag"
    (Get-Date -Format "o") | Set-Content $flagFile -Encoding UTF8

    Write-Output @"
COMPACT NEEDED: pressure=$($pressure.ToString('P0')) static=${l0Tokens}tk calls=${toolCount} session=${sessionMinutes}min
"@
} elseif ($pressure -ge $WARNING_LINE) {
    Write-Output "CONTEXT: $($pressure.ToString('P0')) static=${l0Tokens}tk calls=${toolCount} session=${sessionMinutes}min"
}
