# adapter-lsp.ps1 — Static symbol analyzer + LSP integration bridge
# Extracts symbols from .claude codebase, checks cross-references, detects orphans.
# Complements the LSP tool (goToDefinition/findReferences/documentSymbol) for batch analysis.
#
# Usage:
#   adapter-lsp.ps1 -Index              → build symbol index JSON
#   adapter-lsp.ps1 -Check              → verify cross-references, report broken links
#   adapter-lsp.ps1 -Orphans            → find unreferenced symbols
#   adapter-lsp.ps1 -Query <name>       → find all references to a symbol
#   adapter-lsp.ps1 -Diff               → show symbols changed since last index

param([switch]$Index, [switch]$Check, [switch]$Orphans, [string]$Query, [switch]$Diff)

$ErrorActionPreference = "Continue"
$baseDir = "$env:USERPROFILE\.claude"
$indexFile = "$baseDir\.claude\symbol_index.json"
$scriptsDir = "$baseDir\scripts"

# ═══ PS1 Symbol Extractor ═══
function Get-PS1Symbols($file) {
    $symbols = @()
    $content = Get-Content $file -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return $symbols }

    # Function definitions: function Name { or function Name(
    $funcPattern = 'function\s+(\w[\w-]*)\s*[\{\(]'
    $matches = [regex]::Matches($content, $funcPattern)
    foreach ($m in $matches) {
        $symbols += @{
            name = $m.Groups[1].Value
            type = "function"
            file = $file.Replace($baseDir, "").TrimStart("\").Replace("\", "/")
            line = ($content.Substring(0, $m.Index).Split("`n").Count)
        }
    }

    # PowerShell cmdlet-like names: Verb-Noun pattern (called as functions)
    $cmdletPattern = '\b(\w+-\w[\w-]*)\b'
    $cmdletMatches = [regex]::Matches($content, $cmdletPattern)
    foreach ($m in $cmdletMatches) {
        $name = $m.Groups[1].Value
        if ($name -match '^\w+-\w' -and $name -notin $symbols.name) {
            $symbols += @{
                name = $name
                type = "cmdlet"
                file = $file.Replace($baseDir, "").TrimStart("\").Replace("\", "/")
                line = ($content.Substring(0, $m.Index).Split("`n").Count)
            }
        }
    }
    return $symbols
}

# ═══ Python Symbol Extractor ═══
function Get-PySymbols($file) {
    $symbols = @()
    $content = Get-Content $file -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return $symbols }

    # def function_name(
    $funcPattern = 'def\s+(\w+)\s*\('
    $matches = [regex]::Matches($content, $funcPattern)
    foreach ($m in $matches) {
        $name = $m.Groups[1].Value
        if ($name -notmatch '^_') {  # Skip private
            $symbols += @{
                name = $name
                type = "function"
                file = $file.Replace($baseDir, "").TrimStart("\").Replace("\", "/")
                line = ($content.Substring(0, $m.Index).Split("`n").Count)
            }
        }
    }

    # class ClassName:
    $classPattern = 'class\s+(\w+)\s*[\(:]'
    $matches = [regex]::Matches($content, $classPattern)
    foreach ($m in $matches) {
        $symbols += @{
            name = $m.Groups[1].Value
            type = "class"
            file = $file.Replace($baseDir, "").TrimStart("\").Replace("\", "/")
            line = ($content.Substring(0, $m.Index).Split("`n").Count)
        }
    }
    return $symbols
}

# ═══ Collector ═══
function Get-AllSymbols {
    $all = @()
    # PS1 scripts
    Get-ChildItem $scriptsDir -Recurse -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
        $all += Get-PS1Symbols $_.FullName
    }
    # Python scripts
    Get-ChildItem $scriptsDir -Filter "*.py" -ErrorAction SilentlyContinue | ForEach-Object {
        $all += Get-PySymbols $_.FullName
    }
    return $all
}

# ═══ Cross-Reference Checker ═══
function Get-CrossReferences($symbols) {
    $refs = @{}
    $symbolNames = $symbols | ForEach-Object { $_.name } | Select-Object -Unique

    # Search all PS1 and PY files for references to each symbol
    $allFiles = @(Get-ChildItem $scriptsDir -Recurse -Include "*.ps1","*.py" -ErrorAction SilentlyContinue)
    foreach ($sym in $symbolNames) {
        $refCount = 0
        $refFiles = @()
        foreach ($f in $allFiles) {
            $match = Select-String -Path $f.FullName -Pattern ([regex]::Escape($sym)) -List -ErrorAction SilentlyContinue
            if ($match) {
                $refCount++
                $refFiles += $f.FullName.Replace($baseDir, "").TrimStart("\").Replace("\", "/")
            }
        }
        $refs[$sym] = @{ count = $refCount; files = $refFiles }
    }
    return $refs
}

# ═══ Commands ═══

if ($Index) {
    Write-Output "Building symbol index..."
    $symbols = Get-AllSymbols
    $byFile = $symbols | Group-Object file
    # Build PSCustomObject step-by-step to avoid parser issues with -File mode
    $index = New-Object PSObject
    $index | Add-Member -NotePropertyName "generated" -NotePropertyValue (Get-Date -Format "o")
    $index | Add-Member -NotePropertyName "total_symbols" -NotePropertyValue $symbols.Count
    $index | Add-Member -NotePropertyName "total_files" -NotePropertyValue $byFile.Count
    $index | Add-Member -NotePropertyName "symbols" -NotePropertyValue $symbols
    $byFileMap = @{}
    foreach ($g in $byFile) { $byFileMap[$g.Name] = $g.Group }
    $index | Add-Member -NotePropertyName "by_file" -NotePropertyValue $byFileMap -Force
    $index | ConvertTo-Json -Depth 4 | Set-Content $indexFile -Encoding UTF8
    Write-Output "Indexed $($symbols.Count) symbols across $($byFile.Count) files → $indexFile"
    exit 0
}

if ($Check) {
    # Re-index if stale
    if (-not (Test-Path $indexFile) -or ((Get-Date) - [datetime](Get-Content $indexFile -Raw | ConvertFrom-Json).generated).TotalHours -gt 6) {
        Write-Output "Index stale, rebuilding..."
        & "$PSCommandPath" -Index
    }
    $index = Get-Content $indexFile -Raw | ConvertFrom-Json
    $symbols = $index.symbols
    Write-Output "Checking $($symbols.Count) symbols for cross-references..."
    $refs = Get-CrossReferences $symbols

    $issues = @()
    foreach ($sym in $symbols) {
        $r = $refs[$sym.name]
        $definedIn = $sym.file
        # A symbol is "broken" if it's defined but only referenced in its own file AND it's not a private/local name
        $externalRefs = @($r.files | Where-Object { $_ -ne $definedIn })
        if ($r.count -le 1) {
            $issues += "LOW: '$($sym.name)' ($($sym.type) in $($sym.file)) — no external references (possibly unused)"
        }
    }

    $broken = ($issues | Where-Object { $_ -match '^HIGH' }).Count
    $warnings = ($issues | Where-Object { $_ -match '^LOW' }).Count
    Write-Output "Check complete: $broken broken, $warnings unused, $($symbols.Count) total"
    if ($issues.Count -gt 0 -and $issues.Count -le 20) {
        Write-Output ($issues -join "`n")
    }
    exit 0
}

if ($Orphans) {
    if (-not (Test-Path $indexFile)) { Write-Output "No index. Run -Index first."; exit 1 }
    $index = Get-Content $indexFile -Raw | ConvertFrom-Json
    $symbols = $index.symbols
    $refs = Get-CrossReferences $symbols

    Write-Output "═══ ORPHAN SYMBOLS (referenced only in their own file) ═══`n"
    $orphans = $symbols | Where-Object {
        $r = $refs[$_.name]
        $r.count -le 1 -or ($r.files.Count -eq 1 -and $r.files[0] -eq $_.file)
    }
    foreach ($o in $orphans | Sort-Object file) {
        Write-Output "  [$($o.type)] $($o.name) — $($o.file):$($o.line)"
    }
    Write-Output "`n$($orphans.Count) orphan symbols out of $($symbols.Count) total"
    exit 0
}

if ($Query) {
    if (-not (Test-Path $indexFile)) { Write-Output "No index. Run -Index first."; exit 1 }
    $index = Get-Content $indexFile -Raw | ConvertFrom-Json
    $matches = $index.symbols | Where-Object { $_.name -match $Query }
    if ($matches.Count -eq 0) { Write-Output "No symbols match '$Query'"; exit 0 }
    Write-Output "Symbols matching '$Query' ($($matches.Count) found):"
    foreach ($m in $matches | Sort-Object type, file) {
        Write-Output "  [$($m.type)] $($m.name) — $($m.file):$($m.line)"
    }
    exit 0
}

if ($Diff) {
    if (-not (Test-Path $indexFile)) { Write-Output "No index. Run -Index first."; exit 1 }
    $oldIndex = Get-Content $indexFile -Raw | ConvertFrom-Json
    $oldNames = $oldIndex.symbols | ForEach-Object { "$($_.name)@$($_.file)" }
    $newSymbols = Get-AllSymbols
    $newNames = $newSymbols | ForEach-Object { "$($_.name)@$($_.file)" }

    $added = $newNames | Where-Object { $_ -notin $oldNames }
    $removed = $oldNames | Where-Object { $_ -notin $newNames }

    if ($added) { Write-Output "ADDED ($($added.Count)):`n  $($added -join "`n  ")" }
    if ($removed) { Write-Output "`nREMOVED ($($removed.Count)):`n  $($removed -join "`n  ")" }
    if (-not $added -and -not $removed) { Write-Output "No symbol changes since $($oldIndex.generated)" }
    exit 0
}

# Default
Write-Output "Usage: adapter-lsp.ps1 [-Index] [-Check] [-Orphans] [-Query <name>] [-Diff]"
Write-Output "  -Index   : Build/refresh symbol index"
Write-Output "  -Check   : Verify cross-references, report broken links"
Write-Output "  -Orphans : Find unreferenced symbols"
Write-Output "  -Query   : Search symbols by name"
Write-Output "  -Diff    : Show symbol changes since last index"
