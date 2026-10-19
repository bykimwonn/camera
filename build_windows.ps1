$ErrorActionPreference = "Stop"

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Create and activate .venv first. See README.md for setup instructions."
}

& $Python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "BT CURSOR" `
    --icon (Join-Path $PSScriptRoot "assets\bt_cursor.ico") `
    --add-data "assets;assets" `
    --collect-all mediapipe `
    --collect-all cv2 `
    --collect-all PyQt6 `
    --hidden-import mediapipe.python.solutions.face_mesh `
    --hidden-import mediapipe.python.solutions.hands `
    (Join-Path $PSScriptRoot "main.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host "Built: $PSScriptRoot\dist\BT CURSOR.exe" -ForegroundColor Green
