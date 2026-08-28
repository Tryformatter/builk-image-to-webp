$ErrorActionPreference = "Stop"

Write-Host "Building WebP Forge..." -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "WebP-Forge" `
    --icon "assets\tryformatter.ico" `
    --add-data "assets\tryformatter.ico;assets" `
    --hidden-import "PIL.WebPImagePlugin" `
    app.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path -LiteralPath "dist\WebP-Forge.exe")) {
    throw "Build failed: dist\WebP-Forge.exe was not created."
}

Write-Host ""
Write-Host "Build complete: dist\WebP-Forge.exe" -ForegroundColor Green
