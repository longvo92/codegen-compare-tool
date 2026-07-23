"""VS Code-style change minimap: a miniature render of the file's code shape
(one dim block per whitespace-separated token, indentation preserved) with
changed lines striped in their diff colour and a draggable viewport slider.

One minimap covers both panes: ``aligned_rows`` gives a single shared row
sequence, so row *i* is the same vertical position on old and new. The map is
driven off the old editor (its scrollbar mirrors the new one); clicking or
dragging scrolls that editor and the mirror carries the new pane along. Each
row renders the NEW text (the OLD text on delete-only rows) so the shape
follows the resulting file.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

_WIDTH = 92
_BG = '#202124'
_MAX_LINE_H = 4.0    # px per line at most; short files render small, VS Code-like
_MAX_CHAR_W = 3.0    # px per char at most, so short lines don't stretch full width

# dim token colour per mode (ctx = plain code grey); changed rows also get a
# translucent full-width strip so diffs pop on the map
_TOKEN = {'ctx': '#565b62', 'real': '#e8908d', 'minor': '#d8c070', 'moved': '#7fb0d9'}
_STRIP = {
    'real':  QColor(217, 82, 79, 70),
    'minor': QColor(200, 160, 48, 70),
    'moved': QColor(63, 127, 176, 70),
}
_VIEW_FILL = QColor(255, 255, 255, 26)
_VIEW_BORDER = QColor(190, 190, 190, 120)


def _row_text(r):
    return r.new_txt if r.new_txt is not None else (r.old_txt or '')


class Minimap(QWidget):
    def __init__(self, editor):
        super().__init__()
        self._editor = editor
        self._rows = []
        self._maxlen = 1
        self.setFixedWidth(_WIDTH)
        self.setCursor(Qt.PointingHandCursor)
        editor.verticalScrollBar().valueChanged.connect(self.update)
        editor.blockCountChanged.connect(lambda _n: self.update())

    def set_rows(self, rows):
        self._rows = rows
        self._maxlen = max((len(_row_text(r)) for r in rows), default=1) or 1
        self.update()

    # --- geometry ---

    def _line_h(self, n, h):
        return min(_MAX_LINE_H, h / n) if n else _MAX_LINE_H

    def _char_w(self):
        return min((self.width() - 4) / self._maxlen, _MAX_CHAR_W)

    def _visible_rows(self):
        block = self._editor.firstVisibleBlock()
        bh = self._editor.blockBoundingRect(block).height() or self._editor.fontMetrics().height()
        return max(1, int(self._editor.viewport().height() / bh))

    # --- painting ---

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(_BG))
        rows = self._rows
        n = len(rows)
        if not n:
            return
        h = max(self.height(), 1)
        lh = self._line_h(n, h)
        cw = self._char_w()
        bh = max(1, int(lh * 0.8) or 1)
        prev_y = -10
        for i, r in enumerate(rows):
            y = int(i * lh)
            is_change = r.mode != 'ctx'
            # when compressed (<1px/line), collapse overlapping context rows but
            # never drop a change row
            if not is_change and y == prev_y:
                continue
            prev_y = y
            if is_change:
                p.fillRect(0, y, self.width(), bh, _STRIP.get(r.mode, _STRIP['real']))
            token = QColor(_TOKEN.get(r.mode, _TOKEN['ctx']))
            self._paint_tokens(p, _row_text(r), y, cw, bh, token)
        self._paint_viewport(p, n, h, lh)

    def _paint_tokens(self, p, text, y, cw, bh, color):
        j, length = 0, len(text)
        while j < length:
            if text[j] in ' \t':
                j += 1
                continue
            k = j
            while k < length and text[k] not in ' \t':
                k += 1
            x = 2 + j * cw
            w = max(int((k - j) * cw), 1)
            p.fillRect(int(x), y, w, bh, color)
            j = k

    def _paint_viewport(self, p, n, h, lh):
        first = self._editor.firstVisibleBlock().blockNumber()
        count = self._visible_rows()
        y0 = int(first * lh)
        y1 = int(min((first + count) * lh, n * lh))
        p.fillRect(0, y0, self.width(), max(y1 - y0, 2), _VIEW_FILL)
        p.setPen(_VIEW_BORDER)
        p.drawRect(0, y0, self.width() - 1, max(y1 - y0 - 1, 2))

    # --- interaction: click / drag scrolls the driven editor ---

    def mousePressEvent(self, event):
        self._jump(event.position().y())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._jump(event.position().y())

    def _jump(self, y):
        n = len(self._rows)
        if not n:
            return
        lh = self._line_h(n, max(self.height(), 1))
        row = int(y / lh) if lh else 0
        row = max(0, min(n - 1, row))
        # centre the clicked line in the viewport, like VS Code's slider
        count = self._visible_rows()
        self._editor.verticalScrollBar().setValue(max(0, row - count // 2))
