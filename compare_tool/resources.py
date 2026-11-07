"""Where the shipped images and documents live -- in a source checkout and
inside the frozen one-file exe.

Qt-free on purpose: the lookup is plain path arithmetic, so the packaging spec
and the headless tests can use it without importing PySide6. Every getter
returns ``None`` when the file is absent: a missing icon degrades a button to
its text label, it must never take the viewer down.
"""

import sys
from pkgutil import get_data
from pathlib import Path

_PKG = Path(__file__).resolve().parent


def roots():
    """Folders that may hold the shipped resources, best candidate first."""
    frozen = getattr(sys, '_MEIPASS', None)  # PyInstaller onefile unpack dir
    if frozen:
        yield Path(frozen)
    yield _PKG.parent   # source checkout: <repo>/resources beside the package
    yield _PKG          # resources copied inside the package


def find(*parts):
    """First existing file matching ``parts`` under any root, else None."""
    for root in roots():
        p = root.joinpath(*parts)
        if p.is_file():
            return p
    return None


def icon_file(name):
    """Toolbar/button icon by bare name ('nav-next-change').

    SVG first so the glyph stays crisp on a HiDPI screen; the rasterised
    copies are the fallback for a Qt build whose SVG image plugin was stripped.
    """
    return (find('resources', 'icons', 'svg', name + '.svg')
            or find('resources', 'icons', 'png', '48', name + '.png')
            or find('resources', 'icons', 'png', '24', name + '.png'))


def logo_file(name):
    """Logo asset by file name ('logo-full.png', 'app.ico', ...)."""
    return find('resources', 'logo', name)


def doc_file(name):
    """Repo document shipped alongside the app ('CHANGELOG.md', 'LICENSE')."""
    return find(name)


def doc_text(name):
    """Read a document from disk or the package inside a CLI zipapp."""
    path = doc_file(name)
    if path is not None:
        return path.read_text(encoding='utf-8')
    try:
        data = get_data(__package__, name)
    except FileNotFoundError:
        return None
    return data.decode('utf-8') if data is not None else None
