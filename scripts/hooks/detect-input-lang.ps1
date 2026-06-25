# detect-input-lang.ps1 — UserPromptSubmit: detect language of user input
# v3: pipe $prompt directly to python3 stdin (avoids temp file + PS7 reserved '<' operator)
param($prompt)
$ErrorActionPreference = "Continue"

if (-not $prompt -or $prompt.Length -lt 3) { exit 0 }

$markerFile = "$env:USERPROFILE\.claude\session-env\user-lang.txt"

try {
    $result = $prompt | & python3 "$env:USERPROFILE\.claude\scripts\detect-lang.py" 2>$null
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
