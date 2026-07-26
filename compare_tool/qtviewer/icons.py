"""Icon and logo loading for the viewer.

The shipped SVGs are drawn with ``stroke="currentColor"``, which Qt renders as
black -- invisible on this app's dark chrome. So every icon is loaded and then
**tinted**: the pixmap's alpha is kept and its colour replaced (SourceIn), which
works for the SVGs and the rasterised fallbacks alike.

Nothing here raises when an asset is missing (a pip install without the repo's
``resources/`` folder): the caller gets an empty :class:`QIcon` and the button
keeps its text label.
"""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from ..resources import icon_file, logo_file

# icon tint on the dark chrome, and the accent used for the primary action
TINT = '#d7d7d7'
ACCENT = '#7c8cf8'

_cache = {}


def _tinted(pm, color):
    out = QPixmap(pm)
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(color))
    p.end()
    return out


def icon(name, color=TINT, size=20):
    """Tinted :class:`QIcon` for a shipped glyph; empty when it is missing."""
    key = (name, color, size)
    if key in _cache:
        return _cache[key]
    path = icon_file(name)
    ico = QIcon()
    if path is not None:
        pm = QIcon(str(path)).pixmap(size, size)
        if not pm.isNull():
            ico = QIcon(_tinted(pm, color))
    _cache[key] = ico
    return ico


def std_icon(widget, standard_pixmap, color=TINT, size=20):
    """A Qt built-in icon, tinted to match the shipped set.

    Windows' own icons are full colour (a blue folder, a red help ring) and
    would read as decorations dropped into an otherwise monochrome toolbar.
    """
    pm = widget.style().standardIcon(standard_pixmap).pixmap(size, size)
    return QIcon(_tinted(pm, color)) if not pm.isNull() else QIcon()


def app_icon():
    """Window / taskbar icon. ``app.ico`` carries every size 16..256."""
    for name in ('app.ico', 'logo-mark-256.png', 'logo-mark.svg'):
        path = logo_file(name)
        if path is not None:
            ico = QIcon(str(path))
            if not ico.isNull():
                return ico
    return QIcon()


# The shipped lockup's wordmark is near-black on transparent -- correct on a
# white page, all but invisible on this app's dark chrome. So the SVG twin of
# logo-full.png is re-rendered with a light wordmark; the gradient mark itself
# is untouched. The PNG stays the fallback when Qt's SVG module is absent.
_DARK_WORDMARK = (('fill="#0f172a"', 'fill="#e9edf5"'),
                  ('fill="#475569"', 'fill="#9fb0c6"'))


def _dark_lockup(width):
    path = logo_file('logo-full.svg')
    if path is None:
        return None
    try:
        from PySide6.QtSvg import QSvgRenderer
        svg = path.read_text(encoding='utf-8')
        for old, new in _DARK_WORDMARK:
            svg = svg.replace(old, new)
        r = QSvgRenderer(QByteArray(svg.encode('utf-8')))
        if not r.isValid():
            return None
        size = r.defaultSize()
        if size.width() <= 0:
            return None
        pm = QPixmap(width, round(width * size.height() / size.width()))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        r.render(p)
        p.end()
        return pm
    except Exception:
        return None  # no QtSvg in this build: fall back to the raster lockup


def logo_pixmap(width=320, name='logo-full.png'):
    """Horizontal lockup for the landing page and the About box; None if the
    asset is not shipped with this install."""
    pm = _dark_lockup(width)
    if pm is not None:
        return pm
    path = logo_file(name)
    if path is None:
        return None
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    return pm.scaledToWidth(width, Qt.SmoothTransformation)
