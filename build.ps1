$ErrorActionPreference = "Stop"

Write-Host "Building WebP Forge..." -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "WebP-Forge" `
    --hidden-import "PIL.WebPImagePlugin" `
    app.py

Write-Host ""
Write-Host "Build complete: dist\WebP-Forge.exe" -ForegroundColor Green
