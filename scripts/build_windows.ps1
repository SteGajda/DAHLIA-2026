$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

python -m pip install --upgrade pip
python -m pip install -e ".[build]"

nicegui-pack `
    --clean `
    --noconfirm `
    --onefile `
    --windowed `
    --name "DAHLIA-1.1" `
    --add-data "data;data" `
    run_app.py

Write-Host ""
Write-Host "Gotowy plik: dist/DAHLIA-1.1.exe"
