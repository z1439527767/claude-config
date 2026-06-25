# detect-input-lang.ps1 — UserPromptSubmit: detect language of user input
# v2: use temp file to avoid pipe encoding issues with CJK characters
param($prompt)
$ErrorActionPreference = "Continue"

if (-not $prompt -or $prompt.Length -lt 3) { exit 0 }

$tmpFile = "$env:USERPROFILE\.claude\session-env\_lang_input.tmp"
$markerFile = "$env:USERPROFILE\.claude\session-env\user-lang.txt"

try {
    $prompt | Set-Content $tmpFile -Encoding UTF8 -NoNewline
    $result = & python3 "$env:USERPROFILE\.claude\scripts\detect-lang.py" 2>$null < $tmpFile
    if ($LASTEXITCODE -eq 0 -and $result) {
        $lang = $result.Trim()
        if ($lang -and $lang -ne 'und') {
            $lang | Set-Content $markerFile -Encoding UTF8 -NoNewline
            Write-Output "lang=$lang"
        }
    }
} catch {
    # Silent — language detection is best-effort
} finally {
    Remove-Item $tmpFile -ErrorAction SilentlyContinue
}
exit 0
