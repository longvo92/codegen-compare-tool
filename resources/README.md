# CodeGen Compare — GUI Resources

Icon set + app logo for the AUTOSAR CodeGen Compare / code-review tool.
Built for **PySide6** (works with PyQt6 too).

## Layout

```
resources/
├── icons/
│   ├── svg/            # 10 line icons, 24×24, stroke="currentColor" (recolorable)
│   └── png/{24,48}/    # rasterized fallbacks (@1x / @2x, stroke #334155)
├── logo/
│   ├── logo-mark.svg           # square app mark (badge only)
│   ├── logo-full.svg           # horizontal lockup with wordmark
│   ├── logo-mark-{64..512}.png
│   ├── logo-full.png
│   └── app.ico                 # multi-size Windows icon (16→256)
├── resources.qrc       # Qt resource manifest
└── README.md
```

## Icon set

| File | Button | Meaning |
|------|--------|---------|
| `nav-prev-change`  | Previous change | jump up to the previous diff |
| `nav-next-change`  | Next change     | jump down to the next diff |
| `nav-first-change` | First change    | jump to the first diff |
| `nav-last-change`  | Last change     | jump to the last diff |
| `report`           | Report          | open / view the generated report |
| `export`           | Export          | export report (HTML/PDF) |
| `review-accept`    | Accept          | approve the change |
| `review-reject`    | Reject          | reject the change |
| `review-comment`   | Comment         | add a review comment |
| `review-resolved`  | Resolved        | mark thread / change resolved |

## Design tokens

- Grid 24×24, stroke width **2**, round caps & joins.
- Icons use `stroke="currentColor"` → tint them in Qt via stylesheet/palette
  instead of shipping color variants.
- Logo gradient: indigo `#4F46E5` → cyan `#06B6D4`.
- Diff accents: added `#86EFAC` (green), removed `#FCA5A5` (red).

## Using the SVGs in PySide6

Prefer SVG so buttons stay crisp on HiDPI. Two options:

**A. Direct file load**

```python
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QToolButton

btn = QToolButton()
btn.setIcon(QIcon("resources/icons/svg/nav-next-change.svg"))
btn.setToolTip("Next change")
```

**B. Compiled Qt resource (recommended for shipping)**

```bash
pyside6-rcc resources/resources.qrc -o compare_tool/resources_rc.py
```

```python
import compare_tool.resources_rc          # registers :/icons and :/logo
from PySide6.QtGui import QIcon
btn.setIcon(QIcon(":/icons/nav-next-change.svg"))
window.setWindowIcon(QIcon(":/logo/app.ico"))
```

### Recoloring currentColor icons

`QIcon` won't reflow `currentColor` on its own. Either render through
`QSvgRenderer` with a themed palette, or keep it simple and colorize:

```python
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor

def tinted(path, color, size=24):
    pm = QIcon(path).pixmap(size, size)
    p = QPainter(pm)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pm.rect(), QColor(color))
    p.end()
    return QIcon(pm)

accept_icon = tinted("resources/icons/svg/review-accept.svg", "#16A34A")
reject_icon = tinted("resources/icons/svg/review-reject.svg", "#DC2626")
```

Regenerate everything with `gen/build.py` (see chat history) if you tweak a glyph.
