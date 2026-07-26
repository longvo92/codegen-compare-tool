# Build the standalone artifacts into dist\.
#
#   dist\compare-tool.exe   ONE file, needs NOTHING installed on the target --
#                           CLI + side-by-side viewer together, carrying the
#                           app icon and the viewer's image resources:
#                             compare-tool.exe <old> <new>        CLI + HTML report (exit 0/1/2)
#                             compare-tool.exe --qt <old> <new>   viewer, folders loaded
#                             double-click                        viewer (drop the folders in)
#                           Built as a CONSOLE app so terminal runs keep stdout
#                           and the exit code; the viewer hides the console
#                           window at runtime (see packaging\entry.py).
#
#   dist\compare_tool.pyz   optional tiny zipapp (~26 KB) for machines that
#                           already have Python 3.8+. Stdlib only, so the CLI
#                           works anywhere; the viewer additionally needs
#                           PySide6 installed on that machine.
#
# Usage:
#   .\build.ps1             # exe only (needs pyinstaller + PySide6 locally)
#   .\build.ps1 -Pyz        # exe + zipapp
#   .\build.ps1 -PyzOnly    # zipapp only (no PyInstaller / PySide6 needed)

param([switch]$Pyz, [switch]$PyzOnly)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

New-Item -ItemType Directory -Force dist | Out-Null

# --- zipapp (.pyz) ---
if ($Pyz -or $PyzOnly) {
    $entry = @'
import sys

from compare_tool.main import main

sys.exit(main())
'@
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
}

# --- PyInstaller onefile (.exe): CLI + viewer in one binary ---
if (-not $PyzOnly) {
    python -m pip install --upgrade pyinstaller "PySide6>=6.5"
    if ($LASTEXITCODE -ne 0) { throw 'installing build dependencies failed' }
    python -m PyInstaller --noconfirm --clean packaging\compare-tool.spec
    if ($LASTEXITCODE -ne 0) { throw 'pyinstaller build failed' }

    $exe = Join-Path $PSScriptRoot 'dist\compare-tool.exe'
    if (-not (Test-Path $exe)) { throw "build finished but $exe is missing" }
    $mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "OK dist\compare-tool.exe ($mb MB)"
    Write-Host '   CLI:    compare-tool.exe <old> <new>'
    Write-Host '   viewer: compare-tool.exe --qt <old> <new>   (or double-click)'
}
