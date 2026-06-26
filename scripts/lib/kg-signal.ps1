# kg-signal.ps1 — Reusable hook→KG signal emitter
# Dot-source from any hook: . "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
# Then: Write-KgSignal -Source "hook-name" -EntityType "type" -Observations @("obs1","obs2")

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
