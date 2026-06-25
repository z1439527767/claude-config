# metacog-detect.ps1 — Behavioral detectors from session actions
# Sourced by metacog-bridge.ps1; appends to $script:learnings
param($actions, $turnCount, $now)

if (-not $actions -or $actions.Count -eq 0) { return }

# Detector 1: circular_search (3+ consecutive Reads)
$consecutiveReads = 0; $maxConsecutiveReads = 0
foreach ($a in $actions) {
    if ($a.action_type -eq 'read') { $consecutiveReads++; $maxConsecutiveReads = [Math]::Max($maxConsecutiveReads, $consecutiveReads) }
    else { $consecutiveReads = 0 }
}
if ($maxConsecutiveReads -ge 3) {
    $script:learnings += @{
        pattern = "circular_search"; type = "detection"; category = "Search Patterns"
        lesson = "When searching for a pattern, use one broad Grep before narrowing. Multiple sequential read calls on the same target signals thrashing."
        detected_at = $now.ToString("o"); session_turn_count = $turnCount
    }
}

# Detector 2: repeated_file_read (same file 3+ times)
$readCounts = @{}
foreach ($a in $actions) {
    if ($a.tool_name -eq 'Read' -and $a.target_resource -and $a.target_resource -ne 'unknown') {
        if (-not $readCounts[$a.target_resource]) { $readCounts[$a.target_resource] = 0 }
        $readCounts[$a.target_resource]++
    }
}
$hotFiles = ($readCounts.GetEnumerator() | Where-Object { $_.Value -ge 3 } | Sort-Object Value -Descending)
if ($hotFiles.Count -gt 0) {
    $topFiles = ($hotFiles | Select-Object -First 3 | ForEach-Object { "$(Split-Path $_.Name -Leaf) ($($_.Value)x)" }) -join ", "
    $script:learnings += @{
        pattern = "repeated_file_read"; type = "detection"; category = "Search Patterns"
        lesson = "$($hotFiles.Count) files read 3+ times: $topFiles. Different search strategy or caching may save context."
        detected_at = $now.ToString("o"); session_turn_count = $turnCount
    }
}

# Detector 3: consecutive_failures (3+ in a row)
$consecutiveFails = 0; $maxConsecutiveFails = 0
foreach ($a in $actions) {
    if ($a.outcome -eq 'failure') { $consecutiveFails++; $maxConsecutiveFails = [Math]::Max($maxConsecutiveFails, $consecutiveFails) }
    else { $consecutiveFails = 0 }
}
if ($maxConsecutiveFails -ge 3) {
    $script:learnings += @{
        pattern = "consecutive_failures"; type = "detection"; category = "Error Handling"
        lesson = "Session had $maxConsecutiveFails consecutive failures. Circuit breaker should have activated. Review error handling rules."
        detected_at = $now.ToString("o"); session_turn_count = $turnCount
    }
}

# Detector 4: write_heavy_session (>40% Writes in last 20)
$last20 = @($actions | Select-Object -Last 20)
if ($last20.Count -ge 10) {
    $wCount = ($last20 | Where-Object { $_.action_type -eq 'write' }).Count
    $rCount = ($last20 | Where-Object { $_.action_type -eq 'read' }).Count
    if ($wCount -gt $rCount * 0.4 -and $rCount -gt 0) {
        $script:learnings += @{
            pattern = "write_heavy_session"; type = "detection"; category = "Code Quality"
            lesson = "High write-to-read ratio suggests editing without sufficient context. Read before writing — especially files you haven't seen this session."
            detected_at = $now.ToString("o"); session_turn_count = $turnCount
        }
    }
}

# Detector 5: read_before_edit_violation (wrote without prior read)
$readTargets = @{}
foreach ($a in $actions) {
    if ($a.action_type -eq 'read' -and $a.target_resource -and $a.target_resource -ne 'unknown') {
        $readTargets[$a.target_resource] = $true
    }
}
$writesWithoutRead = @()
foreach ($a in $actions) {
    if ($a.action_type -eq 'write' -and $a.target_resource -and $a.target_resource -ne 'unknown') {
        if (-not $readTargets[$a.target_resource]) {
            $fname = Split-Path $a.target_resource -Leaf
            if ($fname -notin $writesWithoutRead) { $writesWithoutRead += $fname }
        }
    }
}
if ($writesWithoutRead.Count -ge 3) {
    $script:learnings += @{
        pattern = "read_before_edit_violation"; type = "detection"; category = "Code Quality"
        lesson = "$($writesWithoutRead.Count) files edited without being read first. Always read before editing to avoid overwriting changes or working from stale context."
        detected_at = $now.ToString("o"); session_turn_count = $turnCount
    }
}

# Detector 6: mono_tool (80%+ same tool in last 15)
$recent15 = @($actions | Select-Object -Last 15)
if ($recent15.Count -ge 10) {
    $toolCounts = @{}
    foreach ($a in $recent15) { if (-not $toolCounts[$a.tool_name]) { $toolCounts[$a.tool_name] = 0 }; $toolCounts[$a.tool_name]++ }
    $maxTool = ($toolCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1)
    if ($maxTool.Value -ge $recent15.Count * 0.8) {
        $script:learnings += @{
            pattern = "mono_tool_dominance"; type = "detection"; category = "Action Patterns"
            lesson = "$($maxTool.Value)/$($recent15.Count) recent actions used '$($maxTool.Name)'. Over-reliance on one tool type suggests tunnel vision."
            detected_at = $now.ToString("o"); session_turn_count = $turnCount
        }
    }
}
