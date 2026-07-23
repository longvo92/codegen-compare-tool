# Build the standalone CodeGen Compare viewer into a single .exe.
# Run from the repo root on Windows (PyInstaller does not cross-compile --
# build on the OS you want the binary for):
#     powershell -ExecutionPolicy Bypass -File packaging\build-viewer.ps1
# Result: dist\CodeGenCompareViewer.exe

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install --upgrade "pyinstaller" "PySide6>=6.5"
python -m PyInstaller --noconfirm --clean packaging\compare-viewer.spec

$exe = Join-Path $root 'dist\CodeGenCompareViewer.exe'
if (Test-Path $exe) {
    $mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "Built $exe ($mb MB)"
} else {
    throw "Build finished but $exe is missing"
}
