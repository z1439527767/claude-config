# detect-input-lang.ps1 — UserPromptSubmit: detect language of user input
# v3: pipe $prompt directly to python stdin (avoids temp file + PS7 reserved '<' operator)
param($prompt)
$ErrorActionPreference = "Continue"

# Feed KG signal (hook→brain bridge)
. "$env:USERPROFILE\.claude\scripts\lib\kg-signal.ps1"
Write-KgSignal -Source "detect-input-lang" -EntityName "hook-detect-input-lang-$(Get-Date -Format 'yyyyMMdd')" -EntityType "hook-execution" -Observations @("detect-input-lang executed at $(Get-Date -Format 'o')") -Priority "low"
if (-not $prompt -or $prompt.Length -lt 3) { exit 0 }

$markerFile = "$env:USERPROFILE\.claude\session-env\user-lang.txt"

try {
    $result = & python "$env:USERPROFILE\.claude\scripts\detect-lang.py" $prompt 2>$null
    if ($LASTEXITCODE -eq 0 -and $result) {
        $lang = $result.Trim()
        if ($lang -and $lang -ne 'und') {
            $lang | Set-Content $markerFile -Encoding UTF8 -NoNewline
            Write-Output "lang=$lang"
        }
    }
} catch {
    # Silent — language detection is best-effort
}
exit 0
