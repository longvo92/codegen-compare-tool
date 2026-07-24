"""Right-hand side of the viewer: the two-pane side-by-side diff.

The whole-file alignment from :func:`compare_tool.view_model.aligned_rows`
gives one row per aligned line, so every row maps to the SAME line number in
both editors (a padded side becomes a blank line). That equal block count is
what makes the two panes scroll in lockstep with a trivial scrollbar mirror.

Row backgrounds follow the report's palette (real = red/green, minor = yellow,
moved = blue, absent side = dim filler); the changed characters inside a line
are highlighted at the exact offsets :func:`view_model.char_span` reports, so
the pane and the HTML report mark identical spans.
"""

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QPainter, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QSplitter,
                               QStackedWidget, QTextEdit, QVBoxLayout, QWidget)

from ..scanner import looks_binary, read_text
from ..view_model import aligned_rows, char_span
from .icons import logo_pixmap
from .minimap import Minimap

_HINT = 'Select a file in the tree to view its diff.'


def _pm(label, added, removed, changed=0):
    """'+2/−1 port' style chip; empty string when nothing changed."""
    bits = []
    if added:
        bits.append('+{}'.format(added))
    if removed:
        bits.append('−{}'.format(removed))
    if changed:
        bits.append('~{}'.format(changed))
    return '{} {}'.format('/'.join(bits), label) if bits else ''


def _semantic_summary(result):
    """Compact AUTOSAR / A2L change rollup for the file header, reusing the
    semantic diffs the scanner already attached (interfaces, SWC ports /
    runnables / events, RTE access points, A2L objects). '' when none."""
    chips = []
    s = result.get('swc')
    if s:
        chips.append(_pm('SWC', len(s['swcs']['added']), len(s['swcs']['removed'])))
        for cat, label in (('ports', 'port'), ('runnables', 'runnable'),
                           ('events', 'event')):
            chips.append(_pm(label, len(s[cat]['added']), len(s[cat]['removed']),
                             len(s[cat]['changed'])))
    d = result.get('ifaces')
    if d:
        chips.append(_pm('interface', len(d['added']), len(d['removed'])))
    t = result.get('rte')
    if t:
        chips.append(_pm('RTE', len(t['added']), len(t['removed'])))
    a = result.get('a2l')
    if a:
        chips.append(_pm('A2L', len(a['added']), len(a['removed'])))
    chips = [c for c in chips if c]
    return 'AUTOSAR / A2L:   ' + '   ·   '.join(chips) if chips else ''

# per-side row background by mode; None = context (editor base colour).
# comment noise is purple, matching its own file verdict, so "only the banner
# moved" is distinguishable at a glance from a renamed identifier (yellow).
_ROW_BG = {
    ('real', 'old'):    '#3a2222', ('real', 'new'):    '#1f3a24',
    ('comment', 'old'): '#332a42', ('comment', 'new'): '#332a42',
    ('minor', 'old'):   '#3c3418', ('minor', 'new'):   '#3c3418',
    ('moved', 'old'):   '#1d2f3e', ('moved', 'new'):   '#1d2f3e',
}
# inline changed-span background by mode/side
_SEG_BG = {
    ('real', 'old'):    '#7a2f2f', ('real', 'new'):    '#2f6e3d',
    ('comment', 'old'): '#6a5490', ('comment', 'new'): '#6a5490',
    ('minor', 'old'):   '#8a6d1f', ('minor', 'new'):   '#8a6d1f',
    ('moved', 'old'):   '#2f5a7a', ('moved', 'new'):   '#2f5a7a',
}
# translucent overlay marking the change the reviewer is currently on, so
# F7/F8 are visibly doing something even when the file fits on screen and
# there is nothing to scroll
_CUR_BG = QColor(255, 255, 255, 34)
_FILLER_BG = '#26272b'   # the absent side of an insert/delete
_ADD_BG = '#1f3a24'
_DEL_BG = '#3a2222'
_BASE_BG = '#232427'


class _Gutter(QWidget):
    """Line-number margin painted by its owning editor."""

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.gutter_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_gutter(event)


class DiffEditor(QPlainTextEdit):
    """Read-only monospace pane with a per-side line-number gutter. The gutter
    shows each row's ORIGINAL file line number (blank on padded rows), not the
    visual row index."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFrameStyle(0)
        f = QFont('Consolas', 10)
        f.setStyleHint(QFont.Monospace)
        self.setFont(f)
        self.setStyleSheet('QPlainTextEdit{{background:{};color:#d4d4d4;'
                           'border:none;}}'.format(_BASE_BG))
        self._nos = []  # per block: line-number string ('' for padding)
        self._gutter = _Gutter(self)
        self.blockCountChanged.connect(lambda _n: self._update_gutter_width())
        self.updateRequest.connect(self._on_update_request)
        self._update_gutter_width()

    def set_numbers(self, nos):
        self._nos = nos
        self._update_gutter_width()
        self._gutter.update()

    def gutter_width(self):
        digits = max((len(s) for s in self._nos), default=1)
        digits = max(digits, 2)
        return 12 + self.fontMetrics().horizontalAdvance('9') * digits

    def _update_gutter_width(self):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _on_update_request(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, event):
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor('#1e1f22'))
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        painter.setPen(QColor('#6a6a6a'))
        h = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                idx = block.blockNumber()
                num = self._nos[idx] if idx < len(self._nos) else ''
                if num:
                    painter.drawText(0, int(top), self._gutter.width() - 6, h,
                                     Qt.AlignRight, num)
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()


class DiffPane(QStackedWidget):
    """Message page (identical / added / deleted / binary / error) OR the
    two-editor side-by-side page. ``show_file`` / ``clear`` are the seam the
    main window drives."""

    def __init__(self):
        super().__init__()
        # landing / message page. The logo only shows on the landing state:
        # a "binary file differs" or "NOT compared" message should read as a
        # verdict about a file, not as a splash screen.
        self._logo = QLabel()
        self._logo.setAlignment(Qt.AlignCenter)
        pm = logo_pixmap(340)
        if pm is not None:
            self._logo.setPixmap(pm)
        self._logo.setVisible(False)
        self._msg = QLabel(_HINT)
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setWordWrap(True)
        self._msg.setStyleSheet('color:#b9b9b9; font-size:13px;')
        msg_page = QWidget()
        ml = QVBoxLayout(msg_page)
        ml.setSpacing(18)
        ml.addStretch(1)
        ml.addWidget(self._logo)
        ml.addWidget(self._msg)
        ml.addStretch(1)

        self._header = QLabel('')
        self._header.setStyleSheet('color:#e8e8e8; padding:6px 10px 0; font-weight:bold;')
        self._sem = QLabel('')
        self._sem.setWordWrap(True)
        self._sem.setStyleSheet('color:#9a9a9a; padding:0 10px 6px; font-size:12px;')
        self._sem.setVisible(False)
        self.old_edit = DiffEditor()
        self.new_edit = DiffEditor()
        self._split = QSplitter(Qt.Horizontal)
        self._split.addWidget(self.old_edit)
        self._split.addWidget(self.new_edit)
        self._split.setSizes([500, 500])
        self.minimap = Minimap(self.old_edit)
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(self._split, 1)
        bl.addWidget(self.minimap)
        diff_page = QWidget()
        dl = QVBoxLayout(diff_page)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(0)
        # header + semantic line stay at their natural (small) height; the
        # editor body takes ALL remaining vertical space (stretch=1), so the
        # two-pane diff fills the pane from just under the header instead of
        # being pushed to the bottom by an oversized header gap
        dl.addWidget(self._header)
        dl.addWidget(self._sem)
        dl.addWidget(body, 1)

        self.addWidget(msg_page)   # index 0
        self.addWidget(diff_page)  # index 1

        self.rows = []
        self._stops = []           # first row of each real/moved change block
        self._head_base = ''       # header without the "change k of N" suffix
        self._pos_text = ''        # "change k of N", mirrored on the action bar
        self._syncing = False
        self._link_scrolls()

    # --- scroll sync: equal block counts make it a straight mirror ---

    def _link_scrolls(self):
        ov, nv = self.old_edit.verticalScrollBar(), self.new_edit.verticalScrollBar()
        oh, nh = self.old_edit.horizontalScrollBar(), self.new_edit.horizontalScrollBar()
        ov.valueChanged.connect(lambda v: self._mirror(nv, v))
        nv.valueChanged.connect(lambda v: self._mirror(ov, v))
        oh.valueChanged.connect(lambda v: self._mirror(nh, v))
        nh.valueChanged.connect(lambda v: self._mirror(oh, v))

    def _mirror(self, bar, value):
        if self._syncing:
            return
        self._syncing = True
        bar.setValue(value)
        self._syncing = False

    # --- public seam ---

    def clear(self):
        self._logo.setVisible(False)
        self._msg.setText(_HINT)
        self.setCurrentIndex(0)

    def show_drop_hint(self, old=None):
        """Landing screen when no folders are chosen yet."""
        if old:
            self._msg.setText('OLD folder:\n{}\n\nNow drop the NEW folder onto '
                              'this window.'.format(old))
        else:
            self._msg.setText('Drag the OLD and NEW folders onto this window\n'
                              '(drop both at once, or one after the other).\n\n'
                              'Or use "Open folders…" in the toolbar.')
        self._logo.setVisible(True)
        self.setCurrentIndex(0)

    def show_file(self, rel, result, old_root, new_root):
        try:
            self._show_file(rel, result, old_root, new_root)
        except Exception as e:
            # rendering re-reads from disk; a failure must stay loud and never
            # masquerade as an empty (== unchanged-looking) diff
            self._message('{}\n\nCould not render — treat as potentially '
                          'changed.\n{}: {}'.format(rel, type(e).__name__, e))

    # --- internals ---

    def _message(self, text):
        self.rows = []
        self._stops = []
        self.minimap.set_rows([])
        self._pos_text = ''
        self._logo.setVisible(False)
        self._msg.setText(text)
        self.setCurrentIndex(0)

    def _show_file(self, rel, result, old_root, new_root):
        status = result.get('status')
        old_p, new_p = Path(old_root) / rel, Path(new_root) / rel
        if status == 'error':
            self._message('{}\n\nNOT compared — treat as potentially changed.\n{}'
                          .format(rel, '; '.join(result.get('notes', []))))
            return
        if result.get('binary'):
            self._message('{}\n\nBinary file differs.'.format(rel))
            return
        if status == 'added':
            if looks_binary(new_p):
                self._message('{}\n\nBinary file added.'.format(rel))
                return
            self._load_one_side(rel, 'Added', read_text(new_p).split('\n'), 'new')
            return
        if status == 'deleted':
            if looks_binary(old_p):
                self._message('{}\n\nBinary file deleted.'.format(rel))
                return
            self._load_one_side(rel, 'Deleted', read_text(old_p).split('\n'), 'old')
            return
        # real-change / ignorable-only / identical all show the two-pane code;
        # identical has no hunks so it renders as plain context (no highlights)
        if status == 'identical' and (looks_binary(old_p) or looks_binary(new_p)):
            self._message('{}\n\nIdentical (binary).'.format(rel))
            return
        old_lines = read_text(old_p).split('\n')
        new_lines = read_text(new_p).split('\n')
        self.rows = aligned_rows(old_lines, new_lines, result.get('hunks', []))
        self._load_rows(rel, status, result)

    def _load_rows(self, rel, status, result=None):
        rows = self.rows
        n_moved = sum(1 for r in rows if r.mode == 'moved')
        head = '{}   ·   {}'.format(rel, status)
        if n_moved:
            head += '   ·   {} moved line(s)'.format(n_moved)
        self._head_base = head
        self._header.setText(head)
        sem = _semantic_summary(result or {})
        self._sem.setText(sem)
        self._sem.setVisible(bool(sem))
        self.old_edit.setPlainText('\n'.join(r.old_txt or '' for r in rows))
        self.new_edit.setPlainText('\n'.join(r.new_txt or '' for r in rows))
        self.old_edit.set_numbers([str(r.old_no) if r.old_no else '' for r in rows])
        self.new_edit.set_numbers([str(r.new_no) if r.new_no else '' for r in rows])
        self.minimap.set_rows(rows)

        for i, r in enumerate(rows):
            if r.mode == 'ctx':
                continue
            # old side
            if r.old_txt is None:
                self._block_bg(self.old_edit, i, _FILLER_BG)
            else:
                self._block_bg(self.old_edit, i, _ROW_BG.get((r.mode, 'old')))
            # new side
            if r.new_txt is None:
                self._block_bg(self.new_edit, i, _FILLER_BG)
            else:
                self._block_bg(self.new_edit, i, _ROW_BG.get((r.mode, 'new')))
            # inline highlight only when both sides present
            if r.old_txt is not None and r.new_txt is not None:
                (o_lo, o_hi), (n_lo, n_hi) = char_span(r.old_txt, r.new_txt)
                self._seg_bg(self.old_edit, i, o_lo, o_hi, _SEG_BG.get((r.mode, 'old')))
                self._seg_bg(self.new_edit, i, n_lo, n_hi, _SEG_BG.get((r.mode, 'new')))
        # navigation stops: first row of each contiguous real/moved block
        self._stops = []
        was_change = False
        for i, r in enumerate(rows):
            is_change = r.mode in ('real', 'moved')
            if is_change and not was_change:
                self._stops.append(i)
            was_change = is_change
        self.setCurrentIndex(1)
        # start at the top of the file; jump to the first change only if there
        # is one (identical / noise-only files stay at line 1)
        if self._stops:
            self._reveal(self._stops[0])
        else:
            self._pos_text = ''
            self.old_edit.setExtraSelections([])
            self.new_edit.setExtraSelections([])
            self.old_edit.verticalScrollBar().setValue(0)

    def _load_one_side(self, rel, label, lines, side):
        self.rows = []
        self._stops = []
        self._pos_text = ''
        self.minimap.set_rows([])
        self._sem.setVisible(False)
        self._header.setText('{}   ·   {}'.format(rel, label))
        edit = self.old_edit if side == 'old' else self.new_edit
        other = self.new_edit if side == 'old' else self.old_edit
        bg = _DEL_BG if side == 'old' else _ADD_BG
        edit.setPlainText('\n'.join(lines))
        edit.set_numbers([str(i + 1) for i in range(len(lines))])
        other.setPlainText('')
        other.set_numbers([])
        for i in range(len(lines)):
            self._block_bg(edit, i, bg)
        self.setCurrentIndex(1)

    def _block_bg(self, editor, block_no, color):
        if not color:
            return
        block = editor.document().findBlockByNumber(block_no)
        cursor = QTextCursor(block)
        fmt = QTextBlockFormat()
        fmt.setBackground(QColor(color))
        cursor.setBlockFormat(fmt)

    def _seg_bg(self, editor, block_no, lo, hi, color):
        if not color or lo >= hi:
            return
        block = editor.document().findBlockByNumber(block_no)
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + lo)
        cursor.setPosition(block.position() + hi, QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(color))
        cursor.setCharFormat(fmt)

    def _reveal(self, row, context=3):
        """Scroll so `row` sits near the TOP of the pane (a few lines of
        context above), not vertically centred -- centring leaves the whole
        upper half blank, which reads as the diff starting 'too low'. The old
        editor drives; the scrollbar mirror carries the new pane along.

        The change block is also highlighted on both sides: without it, a file
        that fits on screen has nothing to scroll and the navigation looks
        dead even though it moved."""
        block = self.old_edit.document().findBlockByNumber(row)
        self.old_edit.setTextCursor(QTextCursor(block))
        # NoWrap: the vertical scrollbar is in lines, so its value is the top
        # visible line index
        self.old_edit.verticalScrollBar().setValue(max(0, row - context))
        self._highlight_block(row)
        self._update_position(row)

    def _highlight_block(self, row):
        """Overlay the whole contiguous change block containing `row`."""
        rows = self.rows
        if not rows or row >= len(rows):
            return
        start = end = row
        while start > 0 and rows[start - 1].mode == rows[row].mode != 'ctx':
            start -= 1
        while end + 1 < len(rows) and rows[end + 1].mode == rows[row].mode != 'ctx':
            end += 1
        for editor in (self.old_edit, self.new_edit):
            sels = []
            for i in range(start, end + 1):
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(_CUR_BG)
                sel.format.setProperty(QTextFormat.FullWidthSelection, True)
                cur = QTextCursor(editor.document().findBlockByNumber(i))
                cur.clearSelection()
                sel.cursor = cur
                sels.append(sel)
            editor.setExtraSelections(sels)

    def _update_position(self, row):
        if not self._stops:
            self._pos_text = ''
            return
        idx = max(i for i, s in enumerate(self._stops) if s <= row) + 1 \
            if any(s <= row for s in self._stops) else 1
        self._pos_text = 'change {} of {}'.format(idx, len(self._stops))
        self._header.setText('{}   ·   {}'.format(self._head_base, self._pos_text))

    def position_text(self):
        """'change 3 of 7' for the action bar; '' when there is nothing to
        step through (identical or noise-only file, or no file open)."""
        return self._pos_text

    # --- change navigation (real/moved blocks; noise is skipped) ---

    def next_change(self):
        if not self._stops:
            return
        cur = self.old_edit.textCursor().blockNumber()
        self._reveal(next((s for s in self._stops if s > cur), self._stops[0]))

    def prev_change(self):
        if not self._stops:
            return
        cur = self.old_edit.textCursor().blockNumber()
        self._reveal(next((s for s in reversed(self._stops) if s < cur), self._stops[-1]))

    def first_change(self):
        if self._stops:
            self._reveal(self._stops[0])

    def last_change(self):
        if self._stops:
            self._reveal(self._stops[-1])
