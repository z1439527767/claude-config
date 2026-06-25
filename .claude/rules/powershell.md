---
paths:
  - "scripts/**/*.ps1"
  - "*.ps1"
---

# PowerShell Rules
> 🥇 Operational | Load: on PowerShell script execution | Scope: all .ps1 scripts | Overrides: N/A

- ErrorActionPreference = "Continue" or "Stop" explicitly set at script top. No implicit defaults.
- All paths absolute. Use `$env:USERPROFILE` or `$PSScriptRoot`, never relative paths.
- Native exe calls: check `$LASTEXITCODE` immediately after `& cmd`.
- Avoid `New-Item -Force` on files — it truncates. Use `if (-not (Test-Path)) { New-Item }`.
- `try/catch` requires `-ErrorAction Stop` on the cmdlet, or it won't catch.
- No `Write-Host` in hook scripts — use `Write-Output` for hook-visible output.
