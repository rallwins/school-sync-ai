<#
Start or stop both apps in their own PowerShell windows (so you can see logs and they keep
running independently of any editor session).

  .\scripts\dev.ps1          # start backend :8000 and frontend :3000 (builds the frontend if needed)
  .\scripts\dev.ps1 -Stop    # stop whatever is listening on those ports

The backend reads backend\.env (Google credentials) and keeps data in backend\data.
#>
param([switch]$Stop)
$root = Split-Path -Parent $PSScriptRoot

function Stop-Ports { foreach ($port in 8000, 3000) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
      ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } } }

Stop-Ports
if ($Stop) { "Stopped."; return }

if (-not (Test-Path "$root\frontend\.next\BUILD_ID")) {
    Write-Host "Building the frontend (first run)..."
    Push-Location "$root\frontend"; npm run build; Pop-Location
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='SchoolSync backend :8000'; cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='SchoolSync frontend :3000'; cd '$root\frontend'; npx next start -p 3000"
Write-Host "Starting... open http://localhost:3000 (give it ~10 seconds)."
