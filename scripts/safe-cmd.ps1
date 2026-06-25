# safe-cmd.ps1 — command safety validation (distilled from Evolver's solidify.js)
# Usage: .\safe-cmd.ps1 -Command "git push" -AllowList @("git","python","pwsh","node","npm")
param(
    [Parameter(Mandatory=$true)]
    [string]$Command,
    [string[]]$AllowList = @("git", "python", "pwsh", "node", "npm", "npx", "pip", "cargo", "go", "gh"),
    [int]$TimeoutSec = 30
)

$ErrorActionPreference = "Stop"

# Extract the base command (first word)
$base = ($Command -split '\s+')[0]
$baseName = if ($base -match '[/\\]') { Split-Path $base -Leaf } else { $base }
$baseName = $baseName -replace '\.exe$', '' -replace '\.cmd$', ''

if ($baseName -notin $AllowList) {
    Write-Error "SAFE-CMD: '$baseName' not in allowlist. Allowed: $($AllowList -join ', ')"
    exit 2
}

# Check for shell injection patterns
$dangerous = @('`', '$(', '$(', ';', '&&', '||', '>', '<', '|', '&')
foreach ($pattern in $dangerous) {
    if ($Command -match [regex]::Escape($pattern)) {
        Write-Error "SAFE-CMD: Dangerous pattern '$pattern' detected in command"
        exit 2
    }
}

Write-Output "SAFE-CMD: OK — $Command"
exit 0
