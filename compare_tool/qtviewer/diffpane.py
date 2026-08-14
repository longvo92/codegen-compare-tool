"""Right-hand side of the viewer: the two-pane side-by-side diff.

The whole-file alignment from :func:`compare_tool.view_model.aligned_rows`
gives one row per aligned line, so every row maps to the SAME line number in
both editors (a padded side becomes a blank line). That equal block count is
what makes the two panes scroll in lockstep with a trivial scrollbar mirror.

Row backgrounds follow the report's palette (removed = red, added = green,
noise = the same pair dimmed, moved = blue, absent side = dim filler); the
changed characters inside a line are highlighted at the exact offsets
:func:`view_model.char_span` reports, so the pane and the HTML report mark
identical spans. Every colour comes from :mod:`compare_tool.theme`, looked up
when it is painted, so the dark/light switch is a repaint.

A category the reviewer switches off is *muted*, not removed: the lines keep
their place and stay readable in one flat grey, and only the surfaces that
answer "where are the changes" -- the minimap and F7/F8 -- stop counting them.

Foreground is the other channel: :mod:`compare_tool.syntax` colours the code
itself, and the two never touch -- the diff owns background, syntax owns text.
"""

from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QKeySequence, QPainter, QPolygonF,
                           QShortcut, QTextBlockFormat, QTextCharFormat,
                           QTextCursor)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QSplitter, QStackedWidget, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from .. import funcname, review, theme
from ..scanner import looks_binary, read_text
from ..syntax import language_for
from ..view_model import (MUTED, SWC_DISPLAY, Row, aligned_rows, char_span,
                          hunk_row_starts, mode_of, mute_rows, row_with)
from . import highlight
from .highlight import CodeHighlighter
from .icons import logo_pixmap
from .minimap import Minimap

_HINT = 'Select a file in the tree to view its diff.'


def _row_labels(rows, old_lines, new_lines, language):
    """The enclosing scope name for every aligned row, so the "current
    function" caption is one list index at scroll time -- no per-scroll
    scan. The CURRENT side names a row; a row that exists only on the
    BASELINE side (a pure deletion) falls back to it. ``None`` where a row
    is inside no named scope, or the language has none."""
    old = funcname.enclosing(old_lines, language)
    new = funcname.enclosing(new_lines, language)
    out = []
    for r in rows:
        lab = new[r.new_no - 1] if r.new_no and r.new_no <= len(new) else None
        if lab is None and r.old_no and r.old_no <= len(old):
            lab = old[r.old_no - 1]
        out.append(lab)
    return out


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
        for cat in SWC_DISPLAY:
            chips.append(_pm(cat.noun, len(s[cat.key]['added']),
                             len(s[cat.key]['removed']), len(s[cat.key]['changed'])))
    d = result.get('ifaces')
    if d:
        chips.append(_pm('Interface', len(d['added']), len(d['removed'])))
    t = result.get('rte')
    if t:
        chips.append(_pm('RTE', len(t['added']), len(t['removed'])))
    a = result.get('a2l')
    if a:
        chips.append(_pm('A2L', len(a['added']), len(a['removed'])))
    chips = [c for c in chips if c]
    return 'AUTOSAR / A2L:   ' + '   ·   '.join(chips) if chips else ''

# per-side row background by mode, as theme roles; None = context (editor base
# colour). Looked up at paint time, so a theme switch is a repaint and never a
# second copy of this table.
#
# One colour language: removed is red, added is green, on every category. Noise
# (comment banners, UUID churn, renames) used to get purple and yellow of its
# own, which made four hues compete for attention in a pane that also carries
# syntax colours now -- and a diff whose colours need a legend is not readable
# at a glance. Noise is the SAME red/green, one notch dimmer: the reviewer still
# has to see which hunks inside a Modified file are the ones that count.
_ROW_BG = {
    ('real', 'old'):    'del-bg',     ('real', 'new'):    'add-bg',
    ('comment', 'old'): 'del-bg-dim', ('comment', 'new'): 'add-bg-dim',
    ('minor', 'old'):   'del-bg-dim', ('minor', 'new'):   'add-bg-dim',
    ('moved', 'old'):   'mv-bg',      ('moved', 'new'):   'mv-bg',
    # a muted row -- a category the reviewer switched off -- keeps its code but
    # loses its diff colour: one flat grey, same on both sides, so the eye
    # passes over it on the way to the change that still counts
    (MUTED, 'old'):     'muted-bg',   (MUTED, 'new'):     'muted-bg',
}
# inline changed-span background by mode/side. No entry for MUTED on purpose:
# marking the changed characters inside a line the rules no longer report would
# undo the whole point of playing it down.
_SEG_BG = {
    ('real', 'old'):    'seg-del-bg',     ('real', 'new'):    'seg-add-bg',
    ('comment', 'old'): 'seg-del-dim-bg', ('comment', 'new'): 'seg-add-dim-bg',
    ('minor', 'old'):   'seg-del-dim-bg', ('minor', 'new'):   'seg-add-dim-bg',
    ('moved', 'old'):   'seg-mv-bg',      ('moved', 'new'):   'seg-mv-bg',
}
def _gutter_tint(mode, real_role):
    """The gutter role for one side of one row: the del/add role on a real
    change, flat grey on a muted (folded-off) row -- same as its code cell,
    see ``_ROW_BG`` -- and no tint at all otherwise (comment/minor still shown
    in dim colour, and moved, neither of which the gutter number joins in)."""
    if mode == 'real':
        return real_role
    if mode == MUTED:
        return 'muted-bg'
    return ''


_ZOOM_MIN, _ZOOM_MAX = 6, 24  # point size clamp for Ctrl+wheel zoom

# The find hits are amber on purpose: red, green and blue already mean removed,
# added and moved, so a fourth hue is the only way a search result can be told
# apart from a verdict about the code. Every occurrence is marked, the one the
# counter is pointing at brighter -- "3 of 8" is only useful if the other seven
# are visible too. (Roles: find-bg / find-cur-bg.)
#
# 'cur-marker' is the gutter arrow on the change the reviewer is on (see
# DiffEditor.set_current_rows), so F7/F8 are visibly doing something even when
# the file fits on screen and there is nothing to scroll. A row-wide wash was
# tried first and dropped: it competed with the del/add/moved row colour it
# sat on top of, reading as a fourth diff category rather than a pointer.


def _qc(role):
    return QColor(theme.c(role))


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
    visual row index.

    Ctrl+wheel is deliberately NOT left to QPlainTextEdit's own handling: its
    built-in zoom stamps an explicit point size onto the document's char
    format, which changes what is on screen without changing ``self.font()`` --
    so the gutter (sized off ``fontMetrics()``) stops matching the code, and
    the two panes drift apart since each one zooms itself alone. Here the
    wheel only reports a step; :class:`DiffPane` applies it to both editors
    through :meth:`set_point_size`, which sets the widget's real font.
    """

    # +1 / -1 per Ctrl+wheel notch; DiffPane applies it to both editors so a
    # zoom on either pane can never leave the other one behind
    zoomStep = Signal(int)

    # room reserved in the gutter for the F7/F8 current-change arrow, past the
    # line number -- fixed, not grown on demand, so the code column does not
    # shift sideways the moment a marker appears or disappears
    _ARROW_W = 12

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFrameStyle(0)
        f = QFont('Consolas', 10)
        f.setStyleHint(QFont.Monospace)
        self.setFont(f)
        self.apply_theme()
        self._nos = []  # per block: line-number string ('' for padding)
        self._tints = []  # per block: gutter role name for a real-change row, or ''
        self._cur_rows = frozenset()  # blocks carrying the current-change arrow
        self._gutter = _Gutter(self)
        self.blockCountChanged.connect(lambda _n: self._update_gutter_width())
        self.updateRequest.connect(self._on_update_request)
        self._update_gutter_width()

    def apply_theme(self):
        self.setStyleSheet('QPlainTextEdit{{background:{};color:{};'
                           'border:none;}}'.format(theme.c('code-bg'),
                                                   theme.c('code-fg')))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.zoomStep.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    def set_point_size(self, pt):
        """Change the actual widget font -- not a char-format overlay -- so
        the gutter's own ``fontMetrics()`` (used for its width and the row
        height it paints text at) tracks the code exactly."""
        f = self.font()
        f.setPointSize(pt)
        self.setFont(f)
        self._update_gutter_width()
        self._gutter.update()

    def set_numbers(self, nos, tints=None):
        """``nos`` is the line-number string per block; ``tints`` is the
        matching gutter role name per block ('gutter-del-bg' / 'gutter-add-bg'
        / '' for no tint), the number column's own real-change wash. Real
        change only -- moved is a different colour language and comment/minor
        stay flat grey when revealed, so neither gets a second tint here."""
        self._nos = nos
        self._tints = tints or []
        self._update_gutter_width()
        self._gutter.update()

    def set_current_rows(self, rows):
        """Blocks (0-based) to mark with the F7/F8 current-change arrow,
        replacing whatever was marked before -- there is only ever one current
        change. Empty ``rows`` clears the marker."""
        rows = frozenset(rows)
        if rows == self._cur_rows:
            return
        self._cur_rows = rows
        self._gutter.update()

    def gutter_width(self):
        digits = max((len(s) for s in self._nos), default=1)
        digits = max(digits, 2)
        return 12 + self.fontMetrics().horizontalAdvance('9') * digits + self._ARROW_W

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
        # draw the numbers in the EDITOR's font, not the gutter widget's
        # default: the width and row height are already measured off
        # self.fontMetrics(), so without this the glyphs stay a fixed system
        # size and shrink away from the code as it zooms
        painter.setFont(self.font())
        painter.fillRect(event.rect(), _qc('gutter-bg'))
        # the arrow strip sits PAST the number, so the number keeps the exact
        # right edge it always had -- widening the gutter never moves it
        num_w = self._gutter.width() - self._ARROW_W
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        h = self.fontMetrics().height()
        marker = _qc('cur-marker')
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                idx = block.blockNumber()
                num = self._nos[idx] if idx < len(self._nos) else ''
                tint = self._tints[idx] if idx < len(self._tints) else ''
                if tint:
                    painter.fillRect(QRectF(0, top, num_w, bottom - top), _qc(tint))
                if num:
                    painter.setPen(_qc('gutter-fg'))
                    painter.drawText(0, int(top), num_w - 6, h, Qt.AlignRight, num)
                if idx in self._cur_rows:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(marker)
                    cy = top + h / 2
                    painter.drawPolygon(QPolygonF([
                        QPointF(num_w + 2, top + 2), QPointF(num_w + 2, top + h - 2),
                        QPointF(self._gutter.width() - 2, cy)]))
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()


class DiffPane(QStackedWidget):
    """Message page (identical / added / deleted / binary / error) OR the
    two-editor side-by-side page. ``show_file`` / ``clear`` are the seam the
    main window drives."""

    # the reviewable change under the cursor moved (a new file was opened, or
    # F7/F8 stepped to another change): the review bar reloads its note
    unitChanged = Signal()

    def __init__(self):
        super().__init__()
        # landing / message page. The logo only shows on the landing state:
        # a "binary file differs" or "NOT compared" message should read as a
        # verdict about a file, not as a splash screen.
        self._logo = QLabel()
        self._logo.setAlignment(Qt.AlignCenter)
        self._load_logo()
        self._logo.setVisible(False)
        self._msg = QLabel(_HINT)
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setWordWrap(True)
        msg_page = QWidget()
        ml = QVBoxLayout(msg_page)
        ml.setSpacing(18)
        ml.addStretch(1)
        ml.addWidget(self._logo)
        ml.addWidget(self._msg)
        ml.addStretch(1)

        self._header = QLabel('')
        # navigation lives in THIS row, beside the file name it steps through --
        # not in a bar of its own at the bottom, which repeated the same
        # "change k of N" this header already carries for four small buttons'
        # worth of height. MainWindow fills this layout with its nav actions
        # once the pane exists; empty here so the pane works standalone.
        self.nav_actions = QHBoxLayout()
        self.nav_actions.setContentsMargins(0, 0, 0, 0)
        self.nav_actions.setSpacing(0)
        # the enclosing function / SHORT-NAME / A2L block of the top visible
        # line -- Beyond Compare's "current function" box, tracking the scroll.
        # Sits between the file name and the nav buttons, its own breadcrumb so
        # it never crowds the (already long) generated file name.
        self._fn = QLabel('')
        self._fn.setVisible(False)
        self._fn.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head_row = QHBoxLayout()
        head_row.setContentsMargins(10, 6, 6, 0)
        head_row.setSpacing(6)
        head_row.addWidget(self._header, 1)
        head_row.addWidget(self._fn)
        head_row.addLayout(self.nav_actions)
        self._sem = QLabel('')
        self._sem.setWordWrap(True)
        self._sem.setVisible(False)
        self.old_edit = DiffEditor()
        self.new_edit = DiffEditor()
        # VS Code-style "sticky scroll": the enclosing function's signature
        # line, pinned at the top of each pane and syntax-coloured to match the
        # code, so a change deep in a 100-line runnable never loses its header.
        # Child of the viewport, so it sits over the text (not the gutter) and
        # holds still while the code scrolls under it; mouse-transparent so the
        # wheel still reaches the editor.
        self._sticky_old = self._make_sticky(self.old_edit)
        self._sticky_new = self._make_sticky(self.new_edit)
        self._zoom_pt = self.old_edit.font().pointSize()
        # either pane can be the one under the mouse; both zoom together, or a
        # reviewer scrolling one side larger to read it would silently leave
        # the other side's font behind
        self.old_edit.zoomStep.connect(self._zoom_by)
        self.new_edit.zoomStep.connect(self._zoom_by)
        # a folder-name banner sits over each editor: OLD on the left, NEW on
        # the right, so which side is which is unmistakable at a glance. Each
        # banner is wrapped INTO the splitter pane, so it tracks the split when
        # the reviewer drags the divider.
        self._old_name = QLabel('')
        self._new_name = QLabel('')
        for lbl in (self._old_name, self._new_name):
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._split = QSplitter(Qt.Horizontal)
        self._split.addWidget(self._pane(self._old_name, self.old_edit))
        self._split.addWidget(self._pane(self._new_name, self.new_edit))
        self._split.setSizes([500, 500])
        self.minimap = Minimap(self.old_edit)
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(self._split, 1)
        bl.addWidget(self.minimap)
        self._find_bar = self._build_find_bar()
        self._find_bar.setVisible(False)

        diff_page = QWidget()
        dl = QVBoxLayout(diff_page)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(0)
        # header + semantic line stay at their natural (small) height; the
        # editor body takes ALL remaining vertical space (stretch=1), so the
        # two-pane diff fills the pane from just under the header instead of
        # being pushed to the bottom by an oversized header gap
        dl.addLayout(head_row)
        dl.addWidget(self._sem)
        dl.addWidget(self._find_bar)
        dl.addWidget(body, 1)

        self.addWidget(msg_page)   # index 0
        self.addWidget(diff_page)  # index 1

        # syntax colouring: one per document, foreground only, so it never
        # touches the diff backgrounds painted below
        self._hl_old = CodeHighlighter(self.old_edit.document())
        self._hl_new = CodeHighlighter(self.new_edit.document())

        self.rows = []
        self._stops = []           # first row of every F7/F8 stop, in file order
        # review.Unit for each entry in _stops, or None for a Comment/
        # Unimportant stop -- those are navigable but never reviewable (see
        # review.REVIEWABLE), so current_unit() must not attach a note to one
        self._stop_units = []
        self._row_fn = []          # enclosing scope name per row, for the caption
        self._muted = ()           # row modes played down in the panes
        self._units = []           # every reviewable review.Unit, file order
        self._rel = None           # file currently shown
        # what show_file was last called with, so a theme switch can re-render
        # the same file from the same arguments instead of half-repainting it
        self._last = None
        self._old_label = None     # (text, tooltip) when OLD is not a plain folder
        self._new_label = None     # ... and the same for CURRENT (a zip source)
        self._cur_idx = 0          # which change (index into _stops / _units)
        self._head_base = ''       # header without the "change k of N" suffix
        self._pos_text = ''        # "change k of N", folded into the header text
        self._syncing = False
        # which editor scrolling is driven from. The old pane normally carries
        # both (the scrollbar mirror follows it), but a whole added/deleted file
        # puts its text in ONE pane and leaves the other empty -- driving from
        # an empty document scrolls nothing at all.
        self._drive = self.old_edit
        self._hits = []            # rows matching the find box, in file order
        self._hit_idx = -1
        # find-hit extraSelections, per editor (old, new): see _paint_selections.
        # The current change is a gutter arrow now (DiffEditor.set_current_rows),
        # not a second extraSelections layer.
        self._sel_match = [[], []]
        self._link_scrolls()
        # the sticky spans a pane's text area, so it has to be re-fitted whenever
        # that width changes: the window resizes or the divider is dragged
        self._split.splitterMoved.connect(lambda *_: self._sticky_geometry())
        # Ctrl+F is where every editor puts find; the pane owns the shortcut so
        # it works wherever the focus sits inside the diff
        QShortcut(QKeySequence.Find, self).activated.connect(self.open_find)
        QShortcut(QKeySequence(Qt.Key_F3), self).activated.connect(self.find_next)
        QShortcut(QKeySequence('Shift+F3'), self).activated.connect(self.find_prev)
        self._style_widgets()

    # --- theme ---

    def _load_logo(self):
        """(Re)build the landing lockup for the current theme. The wordmark is
        near-black on light and light-grey on dark, baked into the pixmap -- so
        without rebuilding it on a theme switch the light-grey wordmark from a
        dark start would sit all but invisible on the light landing page."""
        pm = logo_pixmap(340)
        if pm is not None:
            self._logo.setPixmap(pm)

    def _style_widgets(self):
        """Every stylesheet this pane sets by hand, in one place, so a theme
        switch is one call rather than a hunt through the constructor."""
        self._msg.setStyleSheet('color:{}; font-size:13px;'
                                .format(theme.c('fg-dim')))
        self._header.setStyleSheet('color:{}; font-weight:bold;'
                                   .format(theme.c('fg-strong')))
        self._fn.setStyleSheet('color:{}; font-family:Consolas, monospace; '
                               'font-size:11px;'.format(theme.c('fg-muted')))
        # the pinned line reads as a header ON the code: its own faint band and
        # a bottom rule mark where it ends and the live code begins
        sticky_qss = ('background:{}; color:{}; border-bottom:1px solid {}; '
                      'padding:2px 8px;'.format(theme.c('sticky-bg'),
                                                theme.c('code-fg'),
                                                theme.c('sticky-border')))
        self._sticky_old.setStyleSheet(sticky_qss)
        self._sticky_new.setStyleSheet(sticky_qss)
        self._sem.setStyleSheet('color:{}; padding:0 10px 6px; font-size:12px;'
                                .format(theme.c('fg-dim')))
        self._find_count.setStyleSheet('color:{}; font-size:12px;'
                                       .format(theme.c('st-ign')))
        # neutral strip, coloured only in the OLD/NEW tag text and a thin
        # underline -- a full red/green band would read as a changed diff row
        for lbl, role in ((self._old_name, 'pane-old-accent'),
                          (self._new_name, 'pane-new-accent')):
            lbl.setStyleSheet(
                'background:{}; color:{}; padding:5px 10px; font-weight:bold; '
                'font-size:13px; border-bottom:2px solid {};'
                .format(theme.c('pane-banner-bg'), theme.c(role),
                        theme.c(role)))

    def apply_theme(self):
        """Repaint everything this pane owns in the current theme.

        The file on screen is re-rendered from ``show_file``'s own arguments:
        the row backgrounds are stamped into the document as block formats, so
        a stylesheet swap alone would leave the previous theme's red and green
        sitting in the code."""
        self._style_widgets()
        self._load_logo()  # the wordmark is baked per theme; rebuild it
        for editor, hl in ((self.old_edit, self._hl_old),
                           (self.new_edit, self._hl_new)):
            editor.apply_theme()
            hl.apply_theme()
        self.minimap.update()
        if self._last is None or self.currentIndex() != 1:
            return
        at = self.reading_position()
        self.show_file(*self._last)
        self.restore_reading_position(at)

    def reading_position(self):
        """Where the reviewer is in the file on screen, as an opaque token.

        Re-rendering a file parks on its first change, and a repaint is not a
        navigation command -- so anything that re-renders has to take this
        first and hand it back afterwards. None when there is no file to hold
        a position in."""
        if self.currentIndex() != 1:
            return None
        return (self._rel, self._drive.textCursor().blockNumber(),
                self._drive.verticalScrollBar().value())

    def restore_reading_position(self, at):
        """Put the cursor, the current-change overlay, the `change k of N` and
        the scroll back where :meth:`reading_position` found them.

        Ignored when the file changed underneath it: landing a stale row number
        on a different file would scroll somewhere arbitrary."""
        if not at or at[0] != self._rel or self.currentIndex() != 1:
            return
        _rel, row, scroll = at
        if row < len(self.rows):
            self._drive.setTextCursor(
                QTextCursor(self._drive.document().findBlockByNumber(row)))
            self._highlight_block(row)
            self._update_position(row)
        self._drive.verticalScrollBar().setValue(scroll)
        self.unitChanged.emit()

    @staticmethod
    def _pane(banner, editor):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(banner)
        lay.addWidget(editor, 1)
        return w

    # --- find in this file ---

    def _build_find_bar(self):
        """One-line find strip under the header, hidden until Ctrl+F.

        It searches the ROWS, not the two documents: a row is one aligned pair,
        so a hit is reported once whichever side carries it, and the jump can
        reuse the same reveal-and-highlight the change navigation uses. Both
        panes then land on the same line, which is the whole point of a
        side-by-side view.
        """
        bar = QWidget()
        bar.setObjectName('findbar')
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 4, 6, 4)
        lay.setSpacing(6)
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText('Find in this file…  (Enter next, '
                                           'Shift+Enter previous, Esc close)')
        self._find_edit.setClearButtonEnabled(True)
        self._find_edit.textChanged.connect(self._find_changed)
        self._find_edit.returnPressed.connect(self.find_next)
        self._find_edit.installEventFilter(self)
        self._find_count = QLabel('')
        close = QToolButton()
        close.setText('✕')
        close.setToolTip('Close the find bar (Esc)')
        close.setAutoRaise(True)
        close.clicked.connect(self.close_find)
        lay.addWidget(self._find_edit, 1)
        lay.addWidget(self._find_count)
        lay.addWidget(close)
        return bar

    def eventFilter(self, obj, event):
        # Esc closes, Shift+Enter steps back: QLineEdit has no signal for
        # either, and both are what every find box in every editor does
        if obj is self._find_edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.close_find()
                return True
            if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                    and event.modifiers() & Qt.ShiftModifier):
                self.find_prev()
                return True
        return super().eventFilter(obj, event)

    def open_find(self):
        """Show the find bar and take the focus, selecting what is there so a
        second Ctrl+F starts a new search instead of appending to the old one."""
        if self.currentIndex() != 1:
            return  # nothing to search: landing screen or a message page
        self._find_bar.setVisible(True)
        self._find_edit.setFocus()
        self._find_edit.selectAll()

    def close_find(self):
        self._find_bar.setVisible(False)
        self._hits = []
        self._hit_idx = -1
        self._mark_matches()  # a closed find bar leaves nothing lit behind it
        # the focus goes back to the diff, or the next keystroke would vanish
        # into a hidden box
        self._drive.setFocus()

    def _refresh_find(self):
        """Re-run the current query against the file just loaded.

        The query is KEPT across files on purpose -- "where else does this
        identifier change" is the reason to search a codegen diff at all, and
        retyping it per file is the whole cost of asking. The pane does not
        jump to a hit by itself, though: opening a file parks on its first
        change, and a search from a previous file must not quietly override
        that. Enter or F3 moves.
        """
        self._hits = []
        self._hit_idx = -1
        if not self._find_bar.isVisible():
            self._mark_matches()
            return
        text = self._find_edit.text()
        if not text.strip():
            self._find_count.setText('')
            self._mark_matches()
            return
        self._hits = self.find_matches(text)
        self._find_count.setText('{} match{}'.format(len(self._hits),
                                                     '' if len(self._hits) == 1 else 'es')
                                 if self._hits else 'No match')
        self._mark_matches()

    def _find_changed(self, text):
        self._hits = self.find_matches(text)
        self._hit_idx = -1
        if not text.strip():
            self._find_count.setText('')
            self._mark_matches()  # every path repaints: see _mark_matches
            return
        if not self._hits:
            self._find_count.setText('No match')
            self._mark_matches()
            return
        self.find_next()

    def find_matches(self, text):
        """Row indices containing `text` on either side, case-insensitive.

        Public so the behaviour can be tested without driving the widget: the
        rows are the model, the bar is only a way to walk them.
        """
        text = text.strip().lower()
        if not text:
            return []
        return [i for i, r in enumerate(self.rows)
                if text in (r.old_txt or '').lower()
                or text in (r.new_txt or '').lower()]

    def _goto_hit(self, idx):
        self._hit_idx = idx % len(self._hits)
        self._find_count.setText('{} of {}'.format(self._hit_idx + 1,
                                                   len(self._hits)))
        self._reveal(self._hits[self._hit_idx])
        self._mark_matches()

    def _mark_matches(self):
        """Repaint the search layer from the CURRENT hits: every occurrence in
        amber, the one being stepped through brighter.

        Rebuilt from scratch on every call, and every path through the find box
        calls it -- a query that stops matching (typing on past the last hit)
        has to take its highlights with it, or the pane says 'No match' while
        the old word is still lit, which reads as a wrong answer.
        """
        self._sel_match = [[], []]
        needle = self._find_edit.text().strip().lower()
        cur = self._hits[self._hit_idx] if 0 <= self._hit_idx < len(self._hits) else None
        if needle and self._hits:
            for i, editor in enumerate((self.old_edit, self.new_edit)):
                doc = editor.document()
                for row in self._hits:
                    if doc.blockCount() <= row:
                        continue  # the other side of a one-sided file
                    block = doc.findBlockByNumber(row)
                    line = block.text().lower()
                    colour = _qc('find-cur-bg' if row == cur else 'find-bg')
                    at = line.find(needle)
                    while at >= 0:
                        sel = QTextEdit.ExtraSelection()
                        sel.format.setBackground(colour)
                        c = QTextCursor(block)
                        c.setPosition(block.position() + at)
                        c.setPosition(block.position() + at + len(needle),
                                      QTextCursor.KeepAnchor)
                        sel.cursor = c
                        self._sel_match[i].append(sel)
                        at = line.find(needle, at + len(needle))
        self._paint_selections()

    def find_next(self):
        if not self._hits:
            return
        self._goto_hit(self._hit_idx + 1)

    def find_prev(self):
        if not self._hits:
            return
        self._goto_hit(self._hit_idx - 1)

    def set_old_label(self, text=None, tip=None):
        """Name the BASELINE pane something other than its folder.

        A commit is checked out, or a zip unpacked, into a temp folder whose
        name says nothing -- for a commit it is even the codegen folder's own,
        so both banners would read the same word. The banner has to say *which*
        version is on the left, so it shows the commit / zip instead. None puts
        the folder name back.
        """
        self._old_label = (text, tip) if text else None

    def set_new_label(self, text=None, tip=None):
        """Name the CURRENT pane something other than its folder -- for a zip
        dropped as the CURRENT side, whose temp path names nothing. None puts
        the folder name back."""
        self._new_label = (text, tip) if text else None

    def _set_pane_names(self, old_root, new_root):
        """Name each pane by its folder: a coloured BASELINE/CURRENT tag then
        the folder name, bright, with the full path as a tooltip. Called
        wherever a file is shown, so the two roots are in hand. A side backed by
        a commit or a zip shows that label instead of the temp folder it was
        materialised into."""
        for lbl, root, tag, role, override in (
                (self._old_name, old_root, 'BASELINE', 'pane-old-accent', self._old_label),
                (self._new_name, new_root, 'CURRENT', 'pane-new-accent', self._new_label)):
            p = Path(root)
            name, tip = p.name or str(p), str(p)
            if override:
                name, tip = override[0], override[1] or str(p)
            lbl.setText('<span style="color:{}">{}</span>'
                        '<span style="color:{}">&nbsp;&nbsp;·&nbsp;&nbsp;{}</span>'
                        .format(theme.c(role), tag, theme.c('fg-strong'), name))
            lbl.setToolTip(tip)

    # --- scroll sync: equal block counts make it a straight mirror ---

    def _link_scrolls(self):
        ov, nv = self.old_edit.verticalScrollBar(), self.new_edit.verticalScrollBar()
        oh, nh = self.old_edit.horizontalScrollBar(), self.new_edit.horizontalScrollBar()
        ov.valueChanged.connect(lambda v: self._mirror(nv, v))
        nv.valueChanged.connect(lambda v: self._mirror(ov, v))
        oh.valueChanged.connect(lambda v: self._mirror(nh, v))
        nh.valueChanged.connect(lambda v: self._mirror(oh, v))
        # the caption and the sticky header track the scroll: whichever pane
        # drives, its top visible line decides which function is named/pinned.
        # Read-only, so they ride on the mirror rather than fighting it.
        ov.valueChanged.connect(self._on_vscroll)
        nv.valueChanged.connect(self._on_vscroll)

    def _mirror(self, bar, value):
        if self._syncing:
            return
        self._syncing = True
        bar.setValue(value)
        self._syncing = False

    def _on_vscroll(self, _value=None):
        self._track_fn()
        self._track_sticky()

    # --- sticky "current function" header (VS Code-style) ---

    @staticmethod
    def _make_sticky(editor):
        lbl = QLabel(editor.viewport())
        lbl.setTextFormat(Qt.RichText)
        lbl.setTextInteractionFlags(Qt.NoTextInteraction)
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents)  # wheel reaches editor
        lbl.setFont(editor.font())
        lbl.setVisible(False)
        return lbl

    def _sticky_geometry(self):
        """Width each sticky spans (the pane's text area) and its height (one
        line plus padding). Called on scroll, resize and zoom -- the viewport
        width changes when the splitter moves or a scrollbar appears."""
        h = self.old_edit.fontMetrics().height() + 8
        for lbl, edit in ((self._sticky_old, self.old_edit),
                          (self._sticky_new, self.new_edit)):
            lbl.setFont(edit.font())
            lbl.setFixedHeight(h)
            lbl.setFixedWidth(edit.viewport().width())
            lbl.move(0, 0)

    def _track_sticky(self, _value=None):
        """Pin the enclosing function's signature line to the top of each pane,
        but only once it has scrolled out of view -- while the real header line
        is on screen there is nothing to pin, same as VS Code.

        C only: a C function opens with a one-line signature that reads on its
        own, so pinning it is useful. An ARXML/A2L scope is a nested
        SHORT-NAME / block chain whose opening line (`<RUNNABLE-ENTITY>`, a
        `/begin`) says nothing by itself -- the caption beside the file name
        already carries that scope for every language."""
        rows = self.rows
        if not rows or not self._rel or language_for(self._rel) != 'c':
            self._hide_sticky()
            return
        top = self._drive.firstVisibleBlock().blockNumber()
        label = self._row_fn[top] if 0 <= top < len(self._row_fn) else None
        if not label:
            self._hide_sticky()
            return
        start = top
        while start > 0 and self._row_fn[start - 1] == label:
            start -= 1
        if start >= top or start >= len(rows):
            self._hide_sticky()  # the signature line itself is the top row
            return
        self._sticky_geometry()
        r = rows[start]
        self._set_sticky(self._sticky_old, r.old_txt, 'c')
        self._set_sticky(self._sticky_new, r.new_txt, 'c')

    def _set_sticky(self, lbl, text, lang):
        if text is None:
            lbl.setVisible(False)
            return
        lbl.setText(highlight.inline_html(text, lang))
        lbl.setVisible(True)
        lbl.raise_()

    def _hide_sticky(self):
        self._sticky_old.setVisible(False)
        self._sticky_new.setVisible(False)

    def _apply_sb_policy(self):
        """One vertical scrollbar, not two: only the driving pane shows one --
        the other is a perfect mirror of it, so a second bar is pure clutter.
        The minimap on the far right carries the overview either way.

        Never on the NEW (right) pane, though: the minimap sits immediately to
        its right, so a bar there collides with it -- the case a whole ADDED
        file hits, where the new pane is the one holding the text and driving.
        Its minimap, the wheel and the keyboard still scroll it."""
        for edit in (self.old_edit, self.new_edit):
            show = edit is self._drive and edit is not self.new_edit
            edit.setVerticalScrollBarPolicy(
                Qt.ScrollBarAsNeeded if show else Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sticky_geometry()  # panes just changed width; re-fit the header

    def _track_fn(self, _value=None):
        """Name, in the caption, the first scope visible from the top of the
        viewport downward. Not strictly the top line: a short file sits with
        its banner and includes on top and the function just below, and the
        function you can see is more use than "no function". The scan is
        bounded to the visible rows, so it never reaches past the screen for a
        scope the reviewer cannot see."""
        if not self._row_fn:
            self._set_fn(None)
            return
        edit = self._drive
        top = edit.firstVisibleBlock().blockNumber()
        line_h = edit.fontMetrics().lineSpacing() or 1
        span = max(1, edit.viewport().height() // line_h)
        for row in range(max(0, top), min(top + span, len(self._row_fn))):
            if self._row_fn[row]:
                self._set_fn(self._row_fn[row])
                return
        self._set_fn(None)

    def _set_fn(self, label):
        self._fn.setText('ƒ ' + label if label else '')  # ƒ, git-style
        self._fn.setVisible(bool(label))

    # --- zoom: both editors always share one size ---

    def _zoom_by(self, step):
        pt = max(_ZOOM_MIN, min(_ZOOM_MAX, self._zoom_pt + step))
        if pt == self._zoom_pt:
            return
        self._zoom_pt = pt
        self.old_edit.set_point_size(pt)
        self.new_edit.set_point_size(pt)
        # block heights just changed under it; its viewport rectangle and
        # visible-row count are computed fresh on every paint, so a repaint is
        # all that is needed to bring the map back in step
        self.minimap.update()
        self._track_sticky()  # the pinned line's font and height moved with it

    # --- public seam ---

    def set_muted_modes(self, modes):
        """Row modes to play down in the panes -- the same categories the
        compare rules stop reporting.

        Unticking `Unimportant` should not leave a wall of red and green in the
        code claiming to be changes; but taking those lines away costs the
        reviewer the context the surviving hunks are read in, and a regenerated
        file is mostly banner churn. So they are greyed, not removed: still
        readable, no diff colour, and gone from the minimap and from F7/F8.

        A TICKED category is the opposite case: Comment and Unimportant hunks
        then keep their own diff colour, same as a real change, and F7/F8
        stops on them too -- so the reviewer can step through everything on
        screen, not just what counts. They still carry no Unit (see
        show_file), so landing on one never offers a note to sign off.

        Takes effect on the next ``show_file``."""
        self._muted = tuple(modes)

    def clear(self):
        self._logo.setVisible(False)
        self._msg.setText(_HINT)
        self._forget_units()
        self._find_bar.setVisible(False)  # no file: nothing to search
        self._hits = []
        self._hit_idx = -1
        self._row_fn = []
        self._set_fn(None)
        self._hide_sticky()
        self._clear_selections()
        self.setCurrentIndex(0)

    def _forget_units(self):
        self._rel = None
        self._last = None
        self._units = []
        self._stop_units = []
        self._cur_idx = 0
        self.unitChanged.emit()

    def show_drop_hint(self, old=None):
        """Landing screen when no folders are chosen yet. Two lines: it is a
        splash, not documentation -- the toolbar buttons are right there, and
        the User guide holds the rest."""
        if old:
            self._msg.setText('BASELINE: {}\n\nNow drop the CURRENT folder.'
                              .format(Path(old).name or old))
        else:
            # the git way in gets a mention: a landing screen that only talks
            # about a pair of folders hides half the tool
            self._msg.setText('Drop the BASELINE and CURRENT folders (or .zip '
                              'artifacts) here.\nOr use "Open folders…" — or '
                              '"Git compare…" for one folder and its own history.')
        self._logo.setVisible(True)
        self._forget_units()
        self.setCurrentIndex(0)

    def show_file(self, rel, result, old_root, new_root):
        self._rel = rel
        self._units = []
        self._cur_idx = 0
        self._last = (rel, result, old_root, new_root)
        try:
            self._show_file(rel, result, old_root, new_root)
        except Exception as e:
            # rendering re-reads from disk; a failure must stay loud and never
            # masquerade as an empty (== unchanged-looking) diff
            self._units = []  # nothing to sign off on a file we could not read
            self._message('{}\n\nCould not render — treat as potentially '
                          'changed.\n{}: {}'.format(rel, type(e).__name__, e))
        self._refresh_find()
        self.unitChanged.emit()

    def file_units(self):
        """Every reviewable unit of the file on screen, in file order.

        Empty when there is nothing to sign off, which is what stops a
        noise-only or unreadable file from being marked reviewed wholesale.
        """
        return list(self._units)

    def current_unit(self):
        """``(rel, key, label)`` of the change the reviewer is looking at, or
        None when there is nothing to sign off here: an identical or
        noise-only file, a path that could not be compared (a note would look
        like a verdict on something nobody read), or -- now that F7/F8 also
        stops on a shown Comment/Unimportant hunk -- the reviewer is standing
        on exactly one of those (see the ``_stop_units`` note in show_file)."""
        if not self._units:
            return None
        if self._units[0].index is None:
            u = self._units[0]  # whole-file unit: added / deleted / binary
        elif self._cur_idx < len(self._stop_units):
            u = self._stop_units[self._cur_idx]
        else:
            return None
        if u is None:
            return None
        return self._rel, u.key, u.label

    # --- internals ---

    def _message(self, text):
        self.rows = []
        self._stops = []
        self._stop_units = []
        self._row_fn = []
        self._set_fn(None)
        self._hide_sticky()
        self._clear_selections()
        self.minimap.set_rows([])
        self._pos_text = ''
        self._logo.setVisible(False)
        self._msg.setText(text)
        self.setCurrentIndex(0)

    def _show_file(self, rel, result, old_root, new_root):
        status = result.get('status')
        old_p, new_p = Path(old_root) / rel, Path(new_root) / rel
        self._set_pane_names(old_root, new_root)
        if status == 'error':
            self._message('{}\n\nNOT compared — treat as potentially changed.\n{}'
                          .format(rel, '; '.join(result.get('notes', []))))
            return
        # units come from the shared seam, never from a local reading of the
        # verdict: the tree's review column counts the same units, and a second
        # copy of "which side does this status need" is how the two start
        # disagreeing about whether a file is fully signed off
        if result.get('binary'):
            # a binary change is still a change to sign off; it is keyed by the
            # file's own bytes, so a regenerated binary drops the signature
            self._units = review.units_of(result, old_p, new_p)
            self._message('{}\n\nBinary file differs.'.format(rel))
            return
        if status in ('added', 'deleted'):
            path = new_p if status == 'added' else old_p
            label = 'Added' if status == 'added' else 'Deleted'
            self._units = review.units_of(result, old_p, new_p)
            if looks_binary(path):
                self._message('{}\n\nBinary file {}.'.format(rel, status))
                return
            lines = read_text(path).split('\n')
            self._load_one_side(rel, label, lines,
                                'new' if status == 'added' else 'old')
            return
        # real-change / ignorable-only / identical all show the two-pane code;
        # identical has no hunks so it renders as plain context (no highlights)
        if status == 'identical' and (looks_binary(old_p) or looks_binary(new_p)):
            self._message('{}\n\nIdentical (binary).'.format(rel))
            return
        old_lines = read_text(old_p).split('\n')
        new_lines = read_text(new_p).split('\n')
        rows = aligned_rows(old_lines, new_lines, result.get('hunks', []))
        # folding is a display choice: the units (and therefore the review keys)
        # come from the hunks, so what a note is attached to never depends on
        # which categories happen to be folded on screen
        self._units = review.units_of(result, old_p, new_p, old_lines, new_lines)
        self.rows = mute_rows(rows, self._muted)
        # scope caption source, aligned to the rows so scrolling is a lookup
        self._row_fn = _row_labels(self.rows, old_lines, new_lines,
                                   language_for(rel))
        self._load_rows(rel, status, result)

    def _load_rows(self, rel, status, result=None):
        rows = self.rows
        n_moved = sum(1 for r in rows if r.mode == 'moved')
        # header names the file only -- the verdict (real-change / identical /
        # …) is already the tree's Status column, so repeating it here was
        # redundant technical noise. The moved-line note and "change k of N"
        # stay: those are about navigating THIS diff, not a repeated label.
        head = rel
        if n_moved:
            head += '   ·   {} Moved line{}'.format(n_moved,
                                                    '' if n_moved == 1 else 's')
        self._head_base = head
        self._header.setText(head)
        sem = _semantic_summary(result or {})
        self._sem.setText(sem)
        self._sem.setVisible(bool(sem))
        # configure before the text lands: setPlainText runs a full highlight
        # pass of its own, so this way the file is coloured once, not twice
        modes = [r.mode for r in rows]
        lang = language_for(rel)
        self._hl_old.configure(lang, modes, repaint=False)
        self._hl_new.configure(lang, modes, repaint=False)
        self._set_text(self.old_edit, '\n'.join(r.old_txt or '' for r in rows))
        self._set_text(self.new_edit, '\n'.join(r.new_txt or '' for r in rows))
        # gutter tint follows the code cell beside it -- a real change gets
        # the del/add wash, a muted (folded-off) row gets the same flat grey
        # its code cell has, so the number column never stops short of a row
        # that is coloured right up to it. Not moved: it already reads as its
        # own thing in blue, and the gutter number was never part of that.
        self.old_edit.set_numbers(
            [str(r.old_no) if r.old_no else '' for r in rows],
            [_gutter_tint(r.mode, 'gutter-del-bg') if r.old_txt is not None else ''
             for r in rows])
        self.new_edit.set_numbers(
            [str(r.new_no) if r.new_no else '' for r in rows],
            [_gutter_tint(r.mode, 'gutter-add-bg') if r.new_txt is not None else ''
             for r in rows])
        # back to the two-pane layout: the old editor drives again (its
        # scrollbar mirror carries the new pane), whatever a previous
        # one-sided file left the map pointing at
        self._drive = self.old_edit
        self._apply_sb_policy()
        self.minimap.set_editor(self.old_edit)
        self.minimap.set_rows(rows)

        for i, r in enumerate(rows):
            if r.mode == 'ctx':
                continue
            # old side
            if r.old_txt is None:
                self._block_bg(self.old_edit, i, theme.c('filler-bg'))
            else:
                self._block_bg(self.old_edit, i, self._bg(r.mode, 'old'))
            # new side
            if r.new_txt is None:
                self._block_bg(self.new_edit, i, theme.c('filler-bg'))
            else:
                self._block_bg(self.new_edit, i, self._bg(r.mode, 'new'))
            # inline highlight only when both sides present, and never on a
            # muted row: there is no _SEG_BG entry for it, so this stays quiet
            if r.mode != MUTED and r.old_txt is not None and r.new_txt is not None:
                (o_lo, o_hi), (n_lo, n_hi) = char_span(r.old_txt, r.new_txt)
                self._seg_bg(self.old_edit, i, o_lo, o_hi, self._seg(r.mode, 'old'))
                self._seg_bg(self.new_edit, i, n_lo, n_hi, self._seg(r.mode, 'new'))
        # navigation stops: the first row of each reviewable change, one per
        # hunk. Deriving them from the hunk list rather than from runs of
        # coloured rows is what makes "change 3 of 7", the hunk count the CLI
        # prints and the units a review note attaches to all the same thing.
        #
        # A Comment or Unimportant hunk is also a stop -- but only while its
        # category is being shown (its mode is not in self._muted): a hunk the
        # reviewer just told the tool to fold away should not make F7/F8 land
        # on it anyway. It carries no Unit (None in _stop_units), so
        # current_unit() reports nothing to sign off there -- noise stays off
        # the review record on purpose (review.REVIEWABLE), navigable or not.
        hunks = (result or {}).get('hunks') or []
        starts = hunk_row_starts(hunks)
        stops = [(starts[u.index], u) for u in self._units
                 if u.index is not None and u.index < len(starts)]
        shown_noise = {'comment', 'minor'} - set(self._muted)
        stops += [(starts[i], None) for i, h in enumerate(hunks)
                  if i < len(starts) and mode_of(h['kind']) in shown_noise]
        stops.sort(key=lambda t: t[0])
        self._stops = [row for row, _u in stops]
        self._stop_units = [u for _row, u in stops]
        self._cur_idx = 0
        self.setCurrentIndex(1)
        # start at the top of the file; jump to the first change only if there
        # is one (identical / noise-only files stay at line 1)
        if self._stops:
            self._reveal(self._stops[0])
        else:
            self._pos_text = ''
            self._clear_selections()
            self.old_edit.verticalScrollBar().setValue(0)
            self._on_vscroll()  # no change to reveal: name the scope at line 1

    def _load_one_side(self, rel, label, lines, side):
        # rows are marked 'ctx': the pane is already one solid colour, so the
        # map has nothing to add by repeating it -- but they ARE the file, and
        # the find box searches rows, so a whole added file has to have them
        self.rows = [Row(None, None, i + 1, line, 'ctx', 'ctx')
                     if side == 'new' else Row(i + 1, line, None, None, 'ctx', 'ctx')
                     for i, line in enumerate(lines)]
        # a one-sided file's rows map 1-1 to its lines, so the caption source
        # is just that side's scope names
        self._row_fn = funcname.enclosing(lines, language_for(rel))
        self._stops = []
        self._stop_units = []
        self._pos_text = ''
        self._clear_selections()  # nothing of the previous file may survive
        self._sem.setVisible(False)
        # keep _head_base in step with the shown header (an added/deleted file
        # has no change stops, but leaving a stale base from the previous file
        # is exactly the kind of drift that bites later)
        self._head_base = '{}   ·   {}'.format(rel, label)
        self._header.setText(self._head_base)
        edit = self.old_edit if side == 'old' else self.new_edit
        other = self.new_edit if side == 'old' else self.old_edit
        bg = theme.c('del-bg' if side == 'old' else 'add-bg')
        # a whole added/deleted file is all one mode, so there are no muted
        # rows to grey out -- the language is the only thing to pass on
        lang = language_for(rel)
        self._hl_old.configure(lang, (), repaint=False)
        self._hl_new.configure(lang, (), repaint=False)
        self._set_text(edit, '\n'.join(lines))
        gutter_tint = 'gutter-del-bg' if side == 'old' else 'gutter-add-bg'
        edit.set_numbers([str(i + 1) for i in range(len(lines))],
                         [gutter_tint] * len(lines))
        self._set_text(other, '')
        other.set_numbers([])
        for i in range(len(lines)):
            self._block_bg(edit, i, bg)
        # the map still shows the file's shape, so a whole added or deleted
        # file scrolls like any other -- driven by the pane that holds the text
        self._drive = edit
        self._apply_sb_policy()
        self.minimap.set_editor(edit)
        self.minimap.set_rows(self.rows)
        self.setCurrentIndex(1)
        self._on_vscroll()

    @staticmethod
    def _bg(mode, side):
        role = _ROW_BG.get((mode, side))
        return theme.c(role) if role else None

    @staticmethod
    def _seg(mode, side):
        role = _SEG_BG.get((mode, side))
        return theme.c(role) if role else None

    @staticmethod
    def _set_text(editor, text):
        """Replace an editor's contents, caret formatting reset first.

        ``setPlainText`` selects the whole new document and stamps the caret's
        char format onto it. Click inside a changed span and the caret picks up
        that span's green; every file opened afterwards then renders entirely
        green, on that pane only, until the caret happens to land somewhere
        plain. Resetting the caret format first is what keeps a click in the
        diff from being a paint tool.
        """
        editor.setCurrentCharFormat(QTextCharFormat())
        editor.setPlainText(text)

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
        drive = self._drive
        block = drive.document().findBlockByNumber(row)
        drive.setTextCursor(QTextCursor(block))
        # NoWrap: the vertical scrollbar is in lines, so its value is the top
        # visible line index
        drive.verticalScrollBar().setValue(max(0, row - context))
        self._highlight_block(row)
        self._update_position(row)
        self._on_vscroll()  # setValue may clamp to a no-op; refresh caption/sticky
        self.unitChanged.emit()

    def _paint_selections(self):
        for i, editor in enumerate((self.old_edit, self.new_edit)):
            editor.setExtraSelections(self._sel_match[i])

    def _clear_selections(self):
        self._sel_match = [[], []]
        self.old_edit.set_current_rows(())
        self.new_edit.set_current_rows(())
        self._paint_selections()

    def _highlight_block(self, row):
        """Mark the whole contiguous change block containing `row` with the
        F7/F8 gutter arrow, on both panes."""
        rows = self.rows
        if not rows or row >= len(rows):
            return
        start = end = row
        while start > 0 and rows[start - 1].mode == rows[row].mode != 'ctx':
            start -= 1
        while end + 1 < len(rows) and rows[end + 1].mode == rows[row].mode != 'ctx':
            end += 1
        cur = range(start, end + 1)
        for editor in (self.old_edit, self.new_edit):
            # a one-sided file leaves the other document empty: marking a
            # block it does not have would land on a block that never renders
            editor.set_current_rows(cur if editor.document().blockCount() > end else ())

    def _update_position(self, row):
        if not self._stops:
            self._pos_text = ''
            return
        idx = max(i for i, s in enumerate(self._stops) if s <= row) + 1 \
            if any(s <= row for s in self._stops) else 1
        self._cur_idx = idx - 1
        self._pos_text = 'Change {} of {}'.format(idx, len(self._stops))
        self._header.setText('{}   ·   {}'.format(self._head_base, self._pos_text))

    # --- change navigation (real/moved blocks; noise is skipped) ---
    #
    # next_change / prev_change stop at the end of THIS file and say so with
    # False instead of wrapping round to the other end. Wrapping inside one
    # file was silent and it dead-ended the review pass: the window catches the
    # False and moves to the next changed file, so F8 walks the whole compare.

    def next_change(self):
        """Step to the next change. False when this file has no next one."""
        if not self._stops:
            return False
        cur = self._drive.textCursor().blockNumber()
        nxt = next((s for s in self._stops if s > cur), None)
        if nxt is None:
            return False
        self._reveal(nxt)
        return True

    def prev_change(self):
        """Step to the previous change. False when this file has no earlier one."""
        if not self._stops:
            return False
        cur = self._drive.textCursor().blockNumber()
        prv = next((s for s in reversed(self._stops) if s < cur), None)
        if prv is None:
            return False
        self._reveal(prv)
        return True

    def goto_name(self, key):
        """Jump to the first changed row naming `key`. True when it landed.

        Used by the quick-changes panel: it knows *what* changed but not where,
        and opening the file at change 1 makes a row about the eighth
        CHARACTERISTIC look like it pointed at the wrong thing. False when the
        name is not in a changed row -- the caller leaves the pane where the
        file's own first change put it rather than scrolling somewhere
        arbitrary.
        """
        i = row_with(self.rows, key)
        if i is None:
            return False
        self._reveal(i)
        return True

    def first_change(self):
        if self._stops:
            self._reveal(self._stops[0])

    def last_change(self):
        if self._stops:
            self._reveal(self._stops[-1])
