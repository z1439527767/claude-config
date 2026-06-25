# verify-scripts-syntax.ps1 — Check all .ps1 scripts for parse errors
param()
$ErrorActionPreference = "Continue"
$scriptDir = "$PSScriptRoot"
$errors = @()

$nullVar = $null
$parseErrors = @()
Get-ChildItem $scriptDir -Recurse -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $nullVar = $null
        $parseErrors = @()
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$nullVar, [ref]$parseErrors)
        if ($parseErrors.Count -gt 0) {
            $errors += "$($_.Name): $($parseErrors.Count) parse error(s)"
        }
    } catch {
        $errors += "$($_.Name): $_"
    }
}

if ($errors.Count -gt 0) {
    Write-Output "SYNTAX ERRORS:`n$($errors -join "`n")"
    exit 1
}

Write-Output "All scripts OK ($((Get-ChildItem $scriptDir -Recurse -Filter '*.ps1').Count) checked)"
exit 0
