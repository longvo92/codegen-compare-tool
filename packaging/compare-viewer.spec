# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the CodeGen Compare side-by-side viewer.
#
# Build (on the SAME OS you want the binary for -- PyInstaller does not
# cross-compile):
#     pyinstaller --noconfirm --clean packaging/compare-viewer.spec
# Output:
#     dist/CodeGenCompareViewer(.exe)   -- one self-contained file, no Python
#     needed on the target machine.

import os

# SPECPATH is the folder holding this spec (…/packaging); the repo root one
# level up must be on the path so `import compare_tool` resolves.
_here = SPECPATH
_root = os.path.dirname(_here)

# The viewer only touches QtCore / QtGui / QtWidgets. PySide6's addons bundle
# QtQuick, WebEngine, 3D, Charts, multimedia, … none of which we use -- exclude
# them so the binary stays as small as PySide6 allows.
_EXCLUDES = [
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D',
    'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2',
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DLogic',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
    'PySide6.QtBluetooth', 'PySide6.QtPositioning', 'PySide6.QtNfc',
    'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtSensors',
    'PySide6.QtSerialPort', 'PySide6.QtSerialBus', 'PySide6.QtPdf',
    'PySide6.QtPdfWidgets', 'PySide6.QtDesigner', 'PySide6.QtHelp',
    'PySide6.QtUiTools', 'PySide6.QtSvgWidgets', 'PySide6.QtNetwork',
    'tkinter',
]

a = Analysis(
    [os.path.join(_here, 'viewer_entry.py')],
    pathex=[_root],
    binaries=[],
    datas=[],
    hiddenimports=[],
    excludes=_EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CodeGenCompareViewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,   # GUI app: no console window
)
