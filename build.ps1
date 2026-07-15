# Build standalone artifacts into dist\ for deployment on servers
# without installing the tool:
#
#   dist\compare_tool.pyz   single file, runs on any machine with Python 3.8+
#                           (python compare_tool.pyz <old> <new> ...)
#   dist\compare_tool.exe   single file, needs NOTHING installed on the target
#                           (built only with -Exe; requires pyinstaller locally:
#                            pip install pyinstaller)
#
# Usage:
#   .\build.ps1          # .pyz only
#   .\build.ps1 -Exe     # .pyz + .exe

param([switch]$Exe)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$entry = @'
import sys

from compare_tool.main import main

sys.exit(main())
'@

New-Item -ItemType Directory -Force dist | Out-Null

# --- zipapp (.pyz) ---
$stage = 'build\zipapp'
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item compare_tool $stage -Recurse
Get-ChildItem $stage -Recurse -Directory -Filter __pycache__ |
    Remove-Item -Recurse -Force
Set-Content "$stage\__main__.py" $entry -Encoding ascii
python -m zipapp $stage -o dist\compare_tool.pyz -c
if ($LASTEXITCODE -ne 0) { throw 'zipapp build failed' }
Write-Host 'OK dist\compare_tool.pyz  (run: python compare_tool.pyz <old> <new>)'

# --- PyInstaller onefile (.exe) ---
if ($Exe) {
    Set-Content 'build\entry_compare_tool.py' $entry -Encoding ascii
    pyinstaller --onefile --name compare_tool --paths . `
        --distpath dist --workpath build\pyinstaller --specpath build `
        build\entry_compare_tool.py
    if ($LASTEXITCODE -ne 0) { throw 'pyinstaller build failed' }
    Write-Host 'OK dist\compare_tool.exe  (run: compare_tool.exe <old> <new>)'
}
