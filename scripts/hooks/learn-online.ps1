# learn-online.ps1 — Self-loop web learning phase
# Searches community for new patterns, compares against current config
param()
$ErrorActionPreference = "Continue"

$base = "$env:USERPROFILE\.claude"
$learnFile = "$base\.claude\learnings.jsonl"
$stateFile = "$base\.claude\learn_state.json"

# Rotate topics — different focus each cycle
$topics = @(
    "claude code hooks best practices 2026",
    "claude code autonomous agent self-improving pattern",
    "claude code settings.json optimization tips",
    "claude code memory persistence cross-session pattern",
    "claude code MCP server useful configuration"
)

# Pick next topic (round-robin)
$state = @{ index = 0 }
if (Test-Path $stateFile) {
    try { $state = Get-Content $stateFile -Raw | ConvertFrom-Json } catch {}
}
$topic = $topics[$state.index % $topics.Count]
$state.index += 1
$state | ConvertTo-Json | Set-Content $stateFile -Encoding UTF8

# Quick web search (output captured, not blocking the cycle)
$searchResult = & curl -s "https://api.duckduckgo.com/?q=$([uri]::EscapeDataString($topic))&format=json" 2>&1
$found = $false

if ($searchResult -match '"FirstURL":"([^"]+)"') {
    $url = $Matches[1]
    $found = $true

    # Log what we found
    $entry = @{
        timestamp = (Get-Date -Format "o")
        topic = $topic
        url = $url
        source = "web"
        status = "found"
    } | ConvertTo-Json -Compress
    Add-Content $learnFile -Value $entry -Encoding UTF8
    Write-Output "LEARN: $topic → $url"
}

if (-not $found) {
    Write-Output "LEARN: $topic → no new results"
}

exit 0
