# dblog.ps1 — PowerShell wrappers for adapter-db.py
# Provides Write-DbLog and Read-DbLog functions for PS hook scripts.
# Dot-source in any hook: . "$env:USERPROFILE\.claude\scripts\lib\dblog.ps1"

$script:DbAdapter = "$env:USERPROFILE\.claude\scripts\adapter-db.py"

function Write-DbLog {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Source,
        [string]$LogKey = "",
        [Parameter(Mandatory=$true)]
        [string]$Data  # JSON string
    )
    try {
        if ($LogKey) {
            $result = python3 $script:DbAdapter insert $Source $LogKey $Data 2>$null
        } else {
            $result = python3 $script:DbAdapter insert $Source $Data 2>$null
        }
        if ($LASTEXITCODE -ne 0) {
            # Silently fall back — JSONL is still the primary write path
        }
    } catch {
        # DB write failure is non-fatal — JSONL is primary
    }
}

function Read-DbLog {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Source,
        [int]$Tail = 50,
        [string]$After = "",
        [string]$Key = "",
        [switch]$AsJson
    )
    try {
        $args = @("query", $Source, "--tail", $Tail)
        if ($After) { $args += "--after"; $args += $After }
        if ($Key) { $args += "--key"; $args += $Key }
        if ($AsJson) { $args += "--json" }

        $result = python3 $script:DbAdapter @args 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            return $result | ConvertFrom-Json
        }
    } catch {
        # Fall back to JSONL read path
    }
    return $null
}

function Remove-DbLog {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Source,
        [Parameter(Mandatory=$true)]
        [int]$Keep
    )
    try {
        python3 $script:DbAdapter rotate $Source --keep $Keep 2>$null | Out-Null
    } catch {}
}

function Get-DbStats {
    try {
        $result = python3 $script:DbAdapter stats 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) { return $result }
    } catch {}
    return "DB unavailable"
}
