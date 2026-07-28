"""Right-hand side of the viewer: the two-pane side-by-side diff.

The whole-file alignment from :func:`compare_tool.view_model.aligned_rows`
gives one row per aligned line, so every row maps to the SAME line number in
both editors (a padded side becomes a blank line). That equal block count is
what makes the two panes scroll in lockstep with a trivial scrollbar mirror.

Row backgrounds follow the report's palette (removed = red, added = green,
noise = the same pair dimmed, moved = blue, absent side = dim filler); the
changed characters inside a line are highlighted at the exact offsets
:func:`view_model.char_span` reports, so the pane and the HTML report mark
identical spans.

Foreground is the other channel: :mod:`compare_tool.syntax` colours the code
itself, and the two never touch -- the diff owns background, syntax owns text.
"""

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QPainter, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QSplitter,
                               QStackedWidget, QTextEdit, QVBoxLayout, QWidget)

from .. import review
from ..scanner import looks_binary, read_text
from ..syntax import language_for
from ..view_model import (aligned_rows, char_span, collapse_rows,
                          hunk_row_starts)
from .highlight import CodeHighlighter
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
#
# One colour language: removed is red, added is green, on every category. Noise
# (comment banners, UUID churn, renames) used to get purple and yellow of its
# own, which made four hues compete for attention in a pane that also carries
# syntax colours now -- and a diff whose colours need a legend is not readable
# at a glance. Noise is the SAME red/green, one notch dimmer: the reviewer still
# has to see which hunks inside a Modified file are the ones that count.
_ROW_BG = {
    ('real', 'old'):    '#3a2222', ('real', 'new'):    '#1f3a24',
    ('comment', 'old'): '#2f2020', ('comment', 'new'): '#1e2f21',
    ('minor', 'old'):   '#2f2020', ('minor', 'new'):   '#1e2f21',
    ('moved', 'old'):   '#1d2f3e', ('moved', 'new'):   '#1d2f3e',
    # a folded run of noise: a flat strip, no diff colour -- it stands for
    # lines the current compare rules say are not a difference at all
    ('folded', 'old'):  '#26272b', ('folded', 'new'):  '#26272b',
}
# a folded placeholder is not code and gets no diff colour; its text says what
# was folded, so the colour does not have to
_FOLD_FG = {'comment': '#8f96a2', 'other': '#8f96a2'}
# inline changed-span background by mode/side
_SEG_BG = {
    ('real', 'old'):    '#7a2f2f', ('real', 'new'):    '#2f6e3d',
    ('comment', 'old'): '#5e2a2a', ('comment', 'new'): '#2c5738',
    ('minor', 'old'):   '#5e2a2a', ('minor', 'new'):   '#2c5738',
    ('moved', 'old'):   '#2f5a7a', ('moved', 'new'):   '#2f5a7a',
}
# translucent overlay marking the change the reviewer is currently on, so
# F7/F8 are visibly doing something even when the file fits on screen and
# there is nothing to scroll
_CUR_BG = QColor(255, 255, 255, 34)
# OLD/NEW pane-banner accents: one source, used for both the tag text and the
# underline so the two can never drift apart
_OLD_ACCENT = '#c98b8b'
_NEW_ACCENT = '#8ec69a'
_FILLER_BG = '#26272b'   # the absent side of an insert/delete
_ADD_BG = '#1f3a24'
_DEL_BG = '#3a2222'
_ZOOM_MIN, _ZOOM_MAX = 6, 24  # point size clamp for Ctrl+wheel zoom
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
        self._header.setStyleSheet('color:#e8e8e8; font-weight:bold;')
        # navigation lives in THIS row, beside the file name it steps through --
        # not in a bar of its own at the bottom, which repeated the same
        # "change k of N" this header already carries for four small buttons'
        # worth of height. MainWindow fills this layout with its nav actions
        # once the pane exists; empty here so the pane works standalone.
        self.nav_actions = QHBoxLayout()
        self.nav_actions.setContentsMargins(0, 0, 0, 0)
        self.nav_actions.setSpacing(0)
        head_row = QHBoxLayout()
        head_row.setContentsMargins(10, 6, 6, 0)
        head_row.setSpacing(6)
        head_row.addWidget(self._header, 1)
        head_row.addLayout(self.nav_actions)
        self._sem = QLabel('')
        self._sem.setWordWrap(True)
        self._sem.setStyleSheet('color:#9a9a9a; padding:0 10px 6px; font-size:12px;')
        self._sem.setVisible(False)
        self.old_edit = DiffEditor()
        self.new_edit = DiffEditor()
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
        self._old_name = self._pane_banner(_OLD_ACCENT)
        self._new_name = self._pane_banner(_NEW_ACCENT)
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
        dl.addWidget(body, 1)

        self.addWidget(msg_page)   # index 0
        self.addWidget(diff_page)  # index 1

        # syntax colouring: one per document, foreground only, so it never
        # touches the diff backgrounds painted below
        self._hl_old = CodeHighlighter(self.old_edit.document())
        self._hl_new = CodeHighlighter(self.new_edit.document())

        self.rows = []
        self._stops = []           # first row of each reviewable change block
        self._fold = ()            # row modes folded out of the panes
        self._units = []           # review.Unit per change, same order as _stops
        self._rel = None           # file currently shown
        self._old_label = None     # (text, tooltip) when OLD is not a folder
        self._cur_idx = 0          # which change (index into _stops / _units)
        self._head_base = ''       # header without the "change k of N" suffix
        self._pos_text = ''        # "change k of N", folded into the header text
        self._syncing = False
        self._link_scrolls()

    @staticmethod
    def _pane_banner(accent):
        # neutral dark strip, coloured only in the OLD/NEW tag text and a thin
        # underline -- a full red/green band would read as a changed diff row
        lbl = QLabel('')
        lbl.setStyleSheet(
            'background:#2a2c31; color:{}; padding:5px 10px; font-weight:bold; '
            'font-size:13px; border-bottom:2px solid {};'.format(accent, accent))
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return lbl

    @staticmethod
    def _pane(banner, editor):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(banner)
        lay.addWidget(editor, 1)
        return w

    def set_old_label(self, text=None, tip=None):
        """Name the BASELINE pane something other than its folder.

        A commit is checked out to a temp folder whose name is the codegen
        folder's own -- both banners would then read the same word. The banner
        has to say *which* version is on the left, so it shows the commit
        instead. None puts the folder name back.
        """
        self._old_label = (text, tip) if text else None

    def _set_pane_names(self, old_root, new_root):
        """Name each pane by its folder: a coloured BASELINE/CURRENT tag then
        the folder name, bright, with the full path as a tooltip. Called
        wherever a file is shown, so the two roots are in hand."""
        for lbl, root, tag, accent in (
                (self._old_name, old_root, 'BASELINE', _OLD_ACCENT),
                (self._new_name, new_root, 'CURRENT', _NEW_ACCENT)):
            p = Path(root)
            name, tip = p.name or str(p), str(p)
            if tag == 'BASELINE' and self._old_label:
                name, tip = self._old_label[0], self._old_label[1] or str(p)
            lbl.setText('<span style="color:{}">{}</span>'
                        '<span style="color:#e8e8e8">&nbsp;&nbsp;·&nbsp;&nbsp;{}</span>'
                        .format(accent, tag, name))
            lbl.setToolTip(tip)

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

    # --- public seam ---

    def set_fold_modes(self, modes):
        """Row modes to fold out of the panes -- the same categories the
        compare rules stop reporting. Unticking `Unimportant` should not leave
        a wall of yellow lines in the code: if those differences do not count,
        showing them is noise. Takes effect on the next ``show_file``."""
        self._fold = tuple(modes)

    def clear(self):
        self._logo.setVisible(False)
        self._msg.setText(_HINT)
        self._forget_units()
        self.setCurrentIndex(0)

    def _forget_units(self):
        self._rel = None
        self._units = []
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
            self._msg.setText('Drop the BASELINE and CURRENT folders here.\n'
                              'Or use "Open folders…" — or "Git compare…" for '
                              'one folder and its own history.')
        self._logo.setVisible(True)
        self._forget_units()
        self.setCurrentIndex(0)

    def show_file(self, rel, result, old_root, new_root):
        self._rel = rel
        self._units = []
        self._cur_idx = 0
        try:
            self._show_file(rel, result, old_root, new_root)
        except Exception as e:
            # rendering re-reads from disk; a failure must stay loud and never
            # masquerade as an empty (== unchanged-looking) diff
            self._units = []  # nothing to sign off on a file we could not read
            self._message('{}\n\nCould not render — treat as potentially '
                          'changed.\n{}: {}'.format(rel, type(e).__name__, e))
        self.unitChanged.emit()

    def file_units(self):
        """Every reviewable unit of the file on screen, in file order.

        Empty when there is nothing to sign off, which is what stops a
        noise-only or unreadable file from being marked reviewed wholesale.
        """
        return list(self._units)

    def current_unit(self):
        """``(rel, key, label)`` of the change the reviewer is looking at, or
        None when this file has nothing to sign off (identical, noise-only, or
        a path that could not be compared -- the last one on purpose: a note
        would look like a verdict on something nobody read)."""
        if not self._units:
            return None
        if self._units[0].index is None:
            u = self._units[0]  # whole-file unit: added / deleted / binary
        elif self._cur_idx < len(self._units):
            u = self._units[self._cur_idx]
        else:
            return None
        return self._rel, u.key, u.label

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
        self.rows, row_map = collapse_rows(rows, self._fold)
        self._load_rows(rel, status, result, row_map)

    def _load_rows(self, rel, status, result=None, row_map=None):
        rows = self.rows
        n_moved = sum(1 for r in rows if r.mode == 'moved')
        # header names the file only -- the verdict (real-change / identical /
        # …) is already the tree's Status column, so repeating it here was
        # redundant technical noise. The moved-line note and "change k of N"
        # stay: those are about navigating THIS diff, not a repeated label.
        head = rel
        if n_moved:
            head += '   ·   {} moved line(s)'.format(n_moved)
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
        self.old_edit.set_numbers([str(r.old_no) if r.old_no else '' for r in rows])
        self.new_edit.set_numbers([str(r.new_no) if r.new_no else '' for r in rows])
        self.minimap.set_rows(rows)

        for i, r in enumerate(rows):
            if r.mode == 'ctx':
                continue
            if r.mode == 'folded':
                fg = _FOLD_FG['comment' if r.kind == 'comment' else 'other']
                for editor in (self.old_edit, self.new_edit):
                    self._block_bg(editor, i, _ROW_BG[('folded', 'old')])
                    self._block_fg(editor, i, fg)
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
        # navigation stops: the first row of each reviewable change, one per
        # hunk. Deriving them from the hunk list rather than from runs of
        # coloured rows is what makes "change 3 of 7", the hunk count the CLI
        # prints and the units a review note attaches to all the same thing.
        starts = hunk_row_starts((result or {}).get('hunks') or [])
        # the starts are positions in the UNFOLDED layout; row_map carries them
        # over. Real and moved rows are never folded, so a stop always lands on
        # the change itself and never inside a placeholder.
        self._stops = [row_map[starts[u.index]] if row_map else starts[u.index]
                       for u in self._units
                       if u.index is not None and u.index < len(starts)]
        self._cur_idx = 0
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
        # keep _head_base in step with the shown header (an added/deleted file
        # has no change stops, but leaving a stale base from the previous file
        # is exactly the kind of drift that bites later)
        self._head_base = '{}   ·   {}'.format(rel, label)
        self._header.setText(self._head_base)
        edit = self.old_edit if side == 'old' else self.new_edit
        other = self.new_edit if side == 'old' else self.old_edit
        bg = _DEL_BG if side == 'old' else _ADD_BG
        # a whole added/deleted file is all one mode, so there are no folded
        # placeholders to skip -- the language is the only thing to pass on
        lang = language_for(rel)
        self._hl_old.configure(lang, (), repaint=False)
        self._hl_new.configure(lang, (), repaint=False)
        self._set_text(edit, '\n'.join(lines))
        edit.set_numbers([str(i + 1) for i in range(len(lines))])
        self._set_text(other, '')
        other.set_numbers([])
        for i in range(len(lines)):
            self._block_bg(edit, i, bg)
        self.setCurrentIndex(1)

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

    def _block_fg(self, editor, block_no, color):
        block = editor.document().findBlockByNumber(block_no)
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.BlockUnderCursor)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.mergeCharFormat(fmt)

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
        self.unitChanged.emit()

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
        self._cur_idx = idx - 1
        self._pos_text = 'change {} of {}'.format(idx, len(self._stops))
        self._header.setText('{}   ·   {}'.format(self._head_base, self._pos_text))

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
