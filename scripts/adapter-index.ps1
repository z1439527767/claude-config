# adapter-index.ps1 — Fast file index for .claude directory
# Build and query a lightweight JSON index to avoid repeated Glob/Grep scans.
# Usage:
#   adapter-index.ps1 -Build             → build/rebuild index
#   adapter-index.ps1 -Query <pattern>   → search index for matching files
#   adapter-index.ps1 -Type ps1          → list all PS1 files from index
#   adapter-index.ps1 -Type py           → list all Python files
#   adapter-index.ps1 -Stale             → check if index is stale (needs rebuild)
param([switch]$Build, [string]$Query, [string]$Type, [switch]$Stale)

$ErrorActionPreference = "Continue"
$baseDir = "$env:USERPROFILE\.claude"
$indexFile = "$baseDir\.claude\file_index.json"
$staleThresholdHours = 6

function Build-Index {
    Write-Output "Building file index..."
    $index = @{
        built_at = (Get-Date -Format "o")
        base_dir = $baseDir
        total_files = 0
        files = @()
    }

    $patterns = @(
        @{ glob = "*.md"; dir = $baseDir; category = "config" },
        @{ glob = "*.json"; dir = $baseDir; category = "config" },
        @{ glob = "*.md"; dir = "$baseDir\.claude\rules"; category = "rules" },
        @{ glob = "*.ps1"; dir = "$baseDir\scripts\hooks"; category = "hooks" },
        @{ glob = "*.ps1"; dir = "$baseDir\scripts\lib"; category = "lib" },
        @{ glob = "*.ps1"; dir = "$baseDir\scripts"; category = "scripts" },
        @{ glob = "*.py"; dir = "$baseDir\scripts"; category = "scripts" },
        @{ glob = "*.md"; dir = "$baseDir\projects\C--Users-z1439--claude\memory"; category = "memory" },
        @{ glob = "*.json"; dir = "$baseDir\projects\C--Users-z1439--claude\memory"; category = "memory" },
        @{ glob = "*.md"; dir = "$baseDir\.claude\skills"; category = "skills" }
    )

    $seen = @{}
    foreach ($p in $patterns) {
        if (-not (Test-Path $p.dir)) { continue }
        Get-ChildItem $p.dir -Filter $p.glob -ErrorAction SilentlyContinue | ForEach-Object {
            $key = $_.FullName.ToLower()
            if (-not $seen[$key]) {
                $seen[$key] = $true
                $index.files += @{
                    rel_path = $_.FullName.Replace($baseDir, "").TrimStart("\").Replace("\", "/")
                    abs_path = $_.FullName
                    name = $_.Name
                    ext = $_.Extension
                    category = $p.category
                    size = $_.Length
                    modified = $_.LastWriteTime.ToString("o")
                }
            }
        }
    }

    $index.total_files = $index.files.Count
    $index | ConvertTo-Json -Depth 3 | Set-Content $indexFile -Encoding UTF8
    Write-Output "Indexed $($index.total_files) files in $baseDir"
}

# ── Stale check ──
if ($Stale) {
    if (-not (Test-Path $indexFile)) {
        Write-Output "STALE: index does not exist. Run -Build first."
        exit 1
    }
    $index = Get-Content $indexFile -Raw | ConvertFrom-Json
    $age = ((Get-Date) - [datetime]$index.built_at).TotalHours
    if ($age -gt $staleThresholdHours) {
        Write-Output "STALE: index is ${age}h old (>${staleThresholdHours}h). Run -Build."
        exit 1
    }
    Write-Output "OK: index is ${age}h old"
    exit 0
}

# ── Build ──
if ($Build) {
    Build-Index
    exit 0
}

# ── Query ──
if ($Query) {
    if (-not (Test-Path $indexFile)) { Write-Output "No index. Run -Build first."; exit 1 }
    $index = Get-Content $indexFile -Raw | ConvertFrom-Json
    $matches = $index.files | Where-Object {
        $_.name -match $Query -or $_.rel_path -match $Query -or $_.category -match $Query
    }
    Write-Output "$($matches.Count) matches for '$Query':"
    foreach ($m in $matches) { Write-Output "  [$($m.category)] $($m.rel_path) ($($m.size) bytes)" }
    exit 0
}

# ── Type filter ──
if ($Type) {
    if (-not (Test-Path $indexFile)) { Write-Output "No index. Run -Build first."; exit 1 }
    $index = Get-Content $indexFile -Raw | ConvertFrom-Json
    $ext = if ($Type -match '^\.') { $Type } else { ".$Type" }
    $matches = $index.files | Where-Object { $_.ext -eq $ext }
    Write-Output "$($matches.Count) files of type ${ext}:"
    foreach ($m in ($matches | Sort-Object category)) { Write-Output "  [$($m.category)] $($m.rel_path)" }
    exit 0
}

# Default
if (Test-Path $indexFile) {
    $index = Get-Content $indexFile -Raw | ConvertFrom-Json
    Write-Output "Index: $($index.total_files) files, built $($index.built_at)"
    Write-Output "  By category:"
    $index.files | Group-Object category | Sort-Object Count -Descending | ForEach-Object {
        Write-Output "    $($_.Name): $($_.Count)"
    }
    Write-Output "Use -Query <pattern>, -Type <ext>, -Build, or -Stale"
} else {
    Write-Output "No index exists. Building now..."
    Build-Index
}
