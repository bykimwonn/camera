$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $python) {
    Write-Error 'Python not found. Install Python 3.11 and/or create the project .venv first.'
    exit 2
}

$logDir = Join-Path $HOME '.gestureflow'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$sessionLog = Join-Path $logDir "session-$stamp.txt"
$motionLog = Join-Path $logDir 'motion.jsonl'
$appLog = Join-Path $logDir 'gestureflow.log'

Write-Host 'Starting GestureFlow with console capture.' -ForegroundColor Cyan
Write-Host "Session output: $sessionLog"
Write-Host "Cursor samples: $motionLog"
Write-Host "Application log: $appLog"
Write-Host 'Use the tray Exit action to stop cleanly. The motion log contains cursor coordinates, not camera images.'
Push-Location $root
try {
    & $python -u (Join-Path $root 'main.py') 2>&1 | Tee-Object -FilePath $sessionLog
    $appExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
Write-Host "GestureFlow exited with code $appExitCode. Logs remain in $logDir" -ForegroundColor Yellow
if ($appExitCode -ne 0) { exit $appExitCode }
