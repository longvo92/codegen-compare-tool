# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the ONE self-contained compare-tool binary: CLI and
# side-by-side viewer in a single file.
#
# Build (on the SAME OS you want the binary for -- PyInstaller does not
# cross-compile):
#     .\build.ps1                     (wrapper, recommended)
#     pyinstaller --noconfirm --clean packaging/compare-tool.spec
# Output:
#     dist/compare-tool(.exe)

import os

# SPECPATH is the folder holding this spec (…/packaging); the repo root one
# level up must be on the path so `import compare_tool` resolves.
_here = SPECPATH
_root = os.path.dirname(_here)

# The viewer is imported lazily (inside a function) so a headless box never
# needs Qt; name it explicitly so the frozen build definitely carries it.
# QtSvg comes along for the icon set: the toolbar glyphs are SVGs, and without
# it Qt's svg image plugin cannot rasterise them (buttons would lose their
# icons and keep only their labels).
_HIDDEN = ['compare_tool.qtviewer.app', 'PySide6.QtSvg']

# Images the viewer loads at runtime, plus the changelog its "Release notes"
# dialog shows. compare_tool.resources looks for them under sys._MEIPASS
# first, which is exactly where these land.
_DATAS = [
    (os.path.join(_root, 'resources', 'icons'), os.path.join('resources', 'icons')),
    (os.path.join(_root, 'resources', 'logo'), os.path.join('resources', 'logo')),
    (os.path.join(_root, 'CHANGELOG.md'), '.'),
]

_ICON = os.path.join(_root, 'resources', 'logo', 'app.ico')

# The viewer only touches QtCore / QtGui / QtWidgets (+ QtSvg for the icons).
# PySide6's addons bundle QtQuick, WebEngine, 3D, Charts, multimedia, … none of
# which we use -- exclude them so the binary stays as small as PySide6 allows.
# tkinter goes too: nothing uses it since the tkinter panel was dropped.
_EXCLUDES = [
    'tkinter', '_tkinter',
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
]

a = Analysis(
    [os.path.join(_here, 'entry.py')],
    pathex=[_root],
    binaries=[],
    datas=_DATAS,
    hiddenimports=_HIDDEN,
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
    name='compare-tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # CONSOLE build on purpose: a terminal run must keep stdout and its exit
    # code (CI gates on exit 1 / 2). The viewer hides the console window at
    # runtime instead -- see packaging/entry.py.
    console=True,
    icon=_ICON if os.path.isfile(_ICON) else None,
)
