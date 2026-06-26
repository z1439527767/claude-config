# kg-signal.ps1 — Reusable hook→KG signal emitter
# Dot-source from any hook: . "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
# Then: Write-KgSignal -Source "hook-name" -EntityType "type" -Observations @("obs1","obs2")
# Priority filter: "low" = hook internals (skipped). "normal"/"high" = actionable (written).

$KG_SIGNAL_FILE = "$env:USERPROFILE\.claude\.claude\kg_signals.jsonl"

function Write-KgSignal {
    param(
        [string]$Source,
        [string]$EntityName,
        [string]$EntityType,
        [string[]]$Observations,
        [hashtable[]]$Relations,
        [string]$Priority = "normal"
    )
    # Filter: low-priority signals are hook execution noise — skip
    if ($Priority -eq "low") { return }

    $signal = @{
        timestamp = (Get-Date -Format "o")
        source    = $Source
        entity    = $EntityName
        entityType = $EntityType
        observations = @($Observations)
        relations = if ($Relations) { @($Relations) } else { @() }
        priority  = $Priority
    }
    $json = $signal | ConvertTo-Json -Compress
    try {
        $json | Add-Content $KG_SIGNAL_FILE -Encoding UTF8
    } catch {
        # Never block on signal failure
    }
}
