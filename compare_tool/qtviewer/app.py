"""Viewer main window: folder tree on the left, diff pane on the right.

The scan runs on a :class:`ScanWorker` thread; the window only reacts to its
signals. Fail-safe stays first-class: a worker crash or any uncompared path
raises a loud red banner -- an incomplete compare must never look clean.
"""

import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QProgressBar, QSizePolicy, QSplitter, QStyle,
                               QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from .. import gitsource, review, theme
from ..diff_engine import RULES
from ..main import default_report_name
from ..report import build_arxml_report, build_report
from ..scanner import apply_fold, summarize
from .dialogs import show_about, show_release_notes, show_user_guide
from .diffpane import DiffPane
from .icons import ACCENT, app_icon, icon, std_icon
from .pickers import pick_commit, pick_folders
from .summary import SummaryPanel
from .tree import (STATUS, build_nodes, filter_nodes, review_color,
                   review_state, status_color)
from .worker import ScanWorker

REL_ROLE = Qt.UserRole      # a FILE row's relative path (folders: None)
PATH_ROLE = Qt.UserRole + 1  # relative path of any row, file or folder
REVIEW_COL = 2               # tree column shown only while review mode is on

# Windows can select the file itself inside its folder; anywhere else the most
# a desktop can be asked for is the folder, and the label must not over-claim
_SHOW_FILE = 'Show in Explorer' if sys.platform == 'win32' \
    else 'Open containing folder'


def _open_in_file_manager(path, select=False):
    """Show `path` in the desktop's file manager.

    Explorer takes ``/select,`` to open the containing folder with the file
    highlighted, which is the whole point of asking from a file row -- a
    codegen folder holds hundreds of files. It also exits non-zero on success,
    so its exit code is deliberately not checked. Everywhere else (and for a
    folder row) the containing folder is handed to the desktop.

    Cosmetic by nature: a failure to open a window must not take the compare
    down, so this reports False instead of raising.
    """
    p = Path(path)
    if select and sys.platform == 'win32':
        # one command string, not an argv list: Explorer parses "/select,<path>"
        # itself and list2cmdline's quoting of that single argument breaks it
        try:
            subprocess.Popen('explorer /select,"{}"'.format(p))
            return True
        except OSError:
            pass  # fall through to the plain folder below
    folder = p.parent if (select or p.is_file()) else p
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def _arxml_include():
    """Same include globs run_compare uses for --arxml-only."""
    return tuple('*' + ext for ext, rs in RULES.items() if rs in ('arxml', 'a2l'))


class _NoteEdit(QPlainTextEdit):
    """Review note box that says when the reviewer leaves it.

    Clicking a diff line moves to another change, so the text has to be written
    back on the way out -- before the cursor lands somewhere else. QPlainTextEdit
    has no editingFinished of its own, hence this."""

    left = Signal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.left.emit()


class MainWindow(QMainWindow):
    def __init__(self, old=None, new=None, exclude=(), arxml_only=False,
                 theme_name=theme.DEFAULT):
        super().__init__()
        self._theme = theme.set_current(theme_name)
        self._state = ('idle', 'Ready')
        self.old = old
        self.new = new
        self.exclude = tuple(exclude)
        self.include = _arxml_include() if arxml_only else ()
        self.arxml_only = arxml_only
        self._raw_results = {}  # verdicts straight from the scan
        self.results = {}       # ... after the current compare rules
        self.worker = None
        self._reviews = review.ReviewStore()  # replaced per scan, see _load_reviews
        self._review_unit = None  # (rel, key, label) the note box is editing
        self._units = {}          # rel -> reviewable units, read once per scan
        self._git_temp = None     # where commits are checked out, this session
        self._old_label = None    # what OLD is, when its folder does not say
        # one scan, one automatic jump to the first change. Flipping a compare
        # rule re-judges the same scan and must NOT drag the reviewer off the
        # file they are reading.
        self._autoselect = False

        self.setWindowTitle('AUTOSAR CodeGen Compare — viewer')
        self.setWindowIcon(app_icon())
        self.resize(1200, 800)
        self.setAcceptDrops(True)  # drop the two folders straight onto the window

        self.banner = QLabel()
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)

        self.tree = QTreeWidget()
        # the Review column exists at all times but is hidden until review mode
        # is on: adding and removing a column would reset the header's own
        # sizing every time the mode is toggled
        self.tree.setHeaderLabels(['File', 'Status', 'Review'])
        self.tree.setColumnHidden(REVIEW_COL, True)
        self.tree.setUniformRowHeights(True)
        # the name column hugs its content instead of taking a fixed 380 px,
        # so Status sits right next to the file name and never gets pushed out
        # of the panel
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self._on_select)
        # right-click a row to open that file where it actually lives -- the
        # reviewer's next step after seeing a diff is often the file itself
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)

        # path search only. Verdicts never remove a row: the folder structure
        # must stay stable so the reviewer's bearings do not shift when change
        # categories are folded away.
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('Filter by path…')
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._refresh_tree)

        # compare-rule toggles: unticking a category means "do not report it
        # separately" -- the tree is rescanned and each such file comes back as
        # Identical (nothing left) or Modified (real changes underneath).
        self.cb_comment = QCheckBox('Comment')
        self.cb_comment.setChecked(True)
        self.cb_comment.setToolTip(
            'Untick to ignore comment-only differences: each such file is then '
            'reported as Identical or Modified.')
        self.cb_comment.toggled.connect(self._apply_rules)
        self.cb_unimportant = QCheckBox('Unimportant')
        self.cb_unimportant.setChecked(True)
        self.cb_unimportant.setToolTip(
            'Untick to ignore the other unimportant differences (UUIDs, '
            'timestamps, renames, whitespace): each such file is then reported '
            'as Identical or Modified.')
        self.cb_unimportant.toggled.connect(self._apply_rules)
        # a display filter, NOT a compare rule: it removes rows from the tree
        # without touching a verdict, which is why it sits apart from the two
        # above. A regenerated tree is mostly untouched files, and scrolling
        # past hundreds of '=' rows to reach five changed ones is its own way
        # of hiding them.
        self.cb_hide_identical = QCheckBox('Hide identical')
        self.cb_hide_identical.setToolTip(
            'Leave only the files with a difference in the tree. Nothing is '
            're-judged: verdicts, counts and the exported report are unchanged. '
            'Files folded to Identical by the two boxes on the left go too.')
        self.cb_hide_identical.toggled.connect(self._refresh_tree_keep_selection)
        rules = QHBoxLayout()
        rules.setContentsMargins(0, 0, 0, 0)
        rules.addWidget(QLabel('Report:'))
        rules.addWidget(self.cb_comment)
        rules.addWidget(self.cb_unimportant)
        rules.addStretch(1)
        rules.addWidget(self.cb_hide_identical)

        tree_box = QWidget()
        lv = QVBoxLayout(tree_box)
        lv.setContentsMargins(6, 6, 6, 0)
        lv.setSpacing(4)
        lv.addWidget(self.filter_edit)
        lv.addLayout(rules)
        lv.addWidget(self.tree, 1)

        # quick-changes rollup under the tree: the same "what changed in the
        # model / calibration" view --arxml-only gives, without leaving the app
        self.summary = SummaryPanel()
        self.summary.fileActivated.connect(self._jump_to_name)
        left = QSplitter(Qt.Vertical)
        left.addWidget(tree_box)
        left.addWidget(self.summary)
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 1)
        left.setSizes([560, 240])

        self.diff = DiffPane()
        self.diff.unitChanged.connect(self._on_unit_changed)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(self.diff)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([400, 800])

        self._make_actions()

        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.banner)
        v.addWidget(split, 1)
        # the review note sits directly under the diff it describes -- hidden
        # until Review mode is on. Navigation lives in the diff pane's own
        # header now, and Export sits in the toolbar next to Review mode.
        self.review_box = self._review_bar()
        self.review_box.setVisible(False)
        v.addWidget(self.review_box)
        self.setCentralWidget(central)

        # status bar: a state chip on the LEFT (Ready / Scanning… / Compare
        # incomplete), the verdict counts as a permanent widget on the right so
        # a transient message can never wipe them, and the progress bar.
        self.state_label = QLabel()
        self.state_label.setTextFormat(Qt.RichText)
        self.state_label.setStyleSheet('padding:0 8px;')
        self.statusBar().addWidget(self.state_label)
        self.counts_label = QLabel('')
        self.statusBar().addPermanentWidget(self.counts_label)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(240)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)
        self._set_state('idle', 'Ready')

        self._build_toolbar()
        self._style_widgets()

        if self.old and self.new:
            self._start_scan()
        else:
            # no folders yet: invite a drag & drop instead of forcing a modal
            # file dialog on the reviewer the moment the app opens. One folder
            # on the command line counts as OLD and waits for its NEW.
            # the chip says the tool's state, nothing else: what to do next is
            # on the landing screen in the middle, in bigger type
            self.diff.show_drop_hint(self.old)
            self._set_state('idle', 'Ready')

    # tool-state chip on the status bar: a coloured dot plus a word, so the
    # reviewer can tell at a glance whether a result is final or still coming
    _STATE_DOT = {'idle': 'state-idle', 'busy': 'state-busy',
                  'ready': 'state-ready', 'error': 'state-error'}

    def _set_state(self, kind, text):
        dot = theme.c(self._STATE_DOT.get(kind, 'state-idle'))
        self._state = (kind, text)
        self.state_label.setText(
            '<span style="color:{}; font-size:15px;">●</span>&nbsp; {}'
            .format(dot, text))

    # --- theme ---

    def _style_widgets(self):
        """The stylesheets this window sets by hand (the rest is the app-wide
        QSS). One place, so a theme switch is one call."""
        self.banner.setStyleSheet(
            'background:{}; color:{}; padding:6px 10px; font-weight:bold; '
            'border-bottom:1px solid {};'.format(
                theme.c('err-bg'), theme.c('err-fg'), theme.c('err-border')))
        self.counts_label.setStyleSheet('color:{}; padding:0 8px;'
                                        .format(theme.c('st-ign')))
        self.review_where.setStyleSheet('color:{}; font-size:11px;'
                                        .format(theme.c('state-idle')))
        self._show_review_file()  # owns review_file's colour: normal or warning

    def _toggle_theme(self):
        self._set_theme(theme.other())

    def _set_theme(self, name):
        """Repaint the whole window in `name`.

        Every surface that stamps a colour into a widget rather than reading it
        from the stylesheet has to be told: the tree's verdict colours, the
        quick-changes rows, the diff pane's block formats, the tinted icons.
        Missing one leaves half the window in the old theme, which is why they
        are listed here and not discovered by walking children.
        """
        changed = theme.set_current(name) != self._theme
        self._theme = theme.current()
        if changed:
            # taken FIRST and handed back LAST: rebuilding the tree re-selects
            # the open file, which re-renders it and parks on its first change.
            # Restoring inside the pane alone would be undone a line later.
            at = self.diff.reading_position()
            apply_theme(QApplication.instance())
            self._style_widgets()
            self._set_state(*self._state)
            self._apply_icons()
            self.summary.apply_theme()
            self.diff.apply_theme()
            self._refresh_tree_keep_selection()  # verdict colours are per item
            self.diff.restore_reading_position(at)
        # outside the guard: the toolbar button is checkable, so Qt has already
        # flipped its state by the time this runs. Skipping the repaint must
        # not leave the button claiming a theme the window is not in.
        self.act_theme.setText(self._theme_label())
        self.act_theme.setChecked(self._theme == theme.LIGHT)

    @staticmethod
    def _theme_label():
        return '☀ Light' if theme.current() == theme.DARK else '☾ Dark'

    def _apply_icons(self):
        """Re-tint every shipped glyph for the current chrome."""
        self.act_open.setIcon(std_icon(self, QStyle.SP_DirOpenIcon))
        for act, glyph, role in self._icon_actions:
            act.setIcon(icon(glyph, role) if role else icon(glyph))
        self.help_button.setIcon(icon('report'))

    # --- actions, toolbar, bottom action bar ---

    def _make_actions(self):
        """Every command the window offers, in one place. The bottom bar and
        the toolbar are just two views of these actions, so a button and its
        shortcut can never drift apart."""
        # (action, glyph, role): what _apply_icons re-tints after a theme
        # switch. A QIcon carries baked pixels, so it cannot follow a palette
        # by itself.
        self._icon_actions = []
        self.act_open = QAction(std_icon(self, QStyle.SP_DirOpenIcon),
                                'Open folders…', self)
        self.act_open.setToolTip('Choose the BASELINE and CURRENT folders — or '
                                 'drop them straight onto the window')
        self.act_open.triggered.connect(self._pick_folders)

        # a way in of its own, not a follow-up to Open folders: this one asks
        # for ONE folder -- the one being reviewed -- and takes the other side
        # from the repository that folder already sits in
        self.act_git = QAction(icon('git-commit'), 'Git compare…', self)
        self.act_git.setToolTip('Compare a folder against one of its own '
                                'commits — no second folder to choose')
        self.act_git.triggered.connect(self._pick_commit)
        self._icon_actions.append((self.act_git, 'git-commit', None))

        # First/Last stay inside the open file -- they mean "this file's ends".
        # Previous/Next run off them into the next file with something to
        # review, so a whole compare can be walked on F7/F8 alone.
        nav = (('act_first', 'nav-first-change', 'First change', 'Ctrl+Home',
                self.diff.first_change, 'in this file'),
               ('act_prev', 'nav-prev-change', 'Previous change', 'F7',
                self._prev_change, 'crosses into the previous changed file'),
               ('act_next', 'nav-next-change', 'Next change', 'F8',
                self._next_change, 'crosses into the next changed file'),
               ('act_last', 'nav-last-change', 'Last change', 'Ctrl+End',
                self.diff.last_change, 'in this file'))
        for attr, glyph, text, key, slot, scope in nav:
            act = QAction(icon(glyph), text, self)
            act.setShortcut(key)
            act.setToolTip('{} ({}) — noise is skipped, {}'.format(text, key, scope))
            act.triggered.connect(slot)
            setattr(self, attr, act)
            self._icon_actions.append((act, glyph, None))
        # these four live in the diff pane's own header, beside the file name
        # they step through -- a bar of their own at the bottom repeated the
        # same "change k of N" the header already shows
        for act in (self.act_first, self.act_prev, self.act_next, self.act_last):
            self.diff.nav_actions.addWidget(self._nav_button(act))

        self.act_export = QAction(icon('export', ACCENT), 'Export report…', self)
        self.act_export.setShortcut('Ctrl+E')
        self.act_export.setEnabled(False)
        self.act_export.setToolTip('Write the full HTML report (Ctrl+E) — always '
                                   'the complete scan, never the folded view')
        self.act_export.triggered.connect(self._export_report)
        self._icon_actions.append((self.act_export, 'export', ACCENT))

        # signing off is a second pass, not part of reading a diff, so the note
        # box stays out of the way until it is asked for -- it was taking a
        # permanent strip of height from the diff for a mode most runs never use
        self.act_review_mode = QAction(icon('review-comment'), 'Review mode', self)
        self.act_review_mode.setCheckable(True)
        self.act_review_mode.setToolTip('Show the note box and sign-off for the '
                                        'current change')
        self.act_review_mode.toggled.connect(self._set_review_mode)
        self._icon_actions.append((self.act_review_mode, 'review-comment', None))

        # text and a sun/moon glyph, no shipped icon: the label names where the
        # click GOES, and reusing another button's glyph for it would make two
        # different commands look like the same one
        self.act_theme = QAction(self._theme_label(), self)
        self.act_theme.setCheckable(True)
        self.act_theme.setChecked(self._theme == theme.LIGHT)
        self.act_theme.setToolTip('Switch the viewer between the dark and the '
                                  'light colour scheme')
        self.act_theme.triggered.connect(self._toggle_theme)

        # no button of its own: the tick in the review bar IS the button. The
        # shortcut exists so a review pass can stay on the keyboard -- F8, tick,
        # F8 -- without reaching for the mouse between every change.
        self.act_reviewed = QAction('Mark this change reviewed', self)
        self.act_reviewed.setShortcut('Ctrl+R')
        self.act_reviewed.triggered.connect(self._toggle_reviewed)

        # a regenerated file is usually one decision spread over a dozen hunks;
        # ticking each one adds clicks without adding scrutiny
        self.act_file_reviewed = QAction('Mark the whole file reviewed', self)
        self.act_file_reviewed.setShortcut('Ctrl+Shift+R')
        self.act_file_reviewed.triggered.connect(self._toggle_file_reviewed)

        self.act_guide = QAction(icon('report'), 'User guide', self)
        self.act_guide.setShortcut('F1')
        self.act_guide.setToolTip('How to use the viewer (F1)')
        self.act_guide.triggered.connect(lambda: show_user_guide(self))
        self._icon_actions.append((self.act_guide, 'report', None))

        self.act_notes = QAction(icon('review-resolved'), 'Release notes', self)
        self.act_notes.setToolTip("What changed in this and earlier versions")
        self.act_notes.triggered.connect(lambda: show_release_notes(self))
        self._icon_actions.append((self.act_notes, 'review-resolved', None))

        self.act_about = QAction(app_icon(), 'About', self)
        self.act_about.setToolTip('Version, author and license')
        self.act_about.triggered.connect(lambda: show_about(self))

        # the bottom-bar buttons do not register shortcuts themselves, so the
        # window must hold these actions for F7/F8/Ctrl+E to fire wherever the
        # focus happens to be
        for act in (self.act_first, self.act_prev, self.act_next,
                    self.act_last, self.act_export, self.act_reviewed,
                    self.act_file_reviewed):
            self.addAction(act)

    def _build_toolbar(self):
        tb = self.addToolBar('main')
        tb.setObjectName('main')
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addAction(self.act_open)
        tb.addAction(self.act_git)
        tb.addSeparator()
        tb.addAction(self.act_review_mode)
        tb.addWidget(self._tool_button(self.act_export, primary=True))
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        # over on the right with Help: both are about the tool, not about the
        # compare, and the left half of the bar is for the latter
        tb.addAction(self.act_theme)
        # the three help pages behind one menu on the right: they are read once
        # and then never again, so three permanent buttons were spending the
        # top bar on the rarest thing in the window
        self.help_button = QToolButton()
        self.help_button.setText('Help')
        self.help_button.setIcon(icon('report'))
        self.help_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.help_button.setIconSize(QSize(20, 20))
        self.help_button.setPopupMode(QToolButton.InstantPopup)
        self.help_button.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self.help_button)  # parented, so it outlives this call
        menu.addAction(self.act_guide)
        menu.addAction(self.act_notes)
        menu.addSeparator()
        menu.addAction(self.act_about)
        self.help_button.setMenu(menu)
        tb.addWidget(self.help_button)

    @staticmethod
    def _tool_button(action, primary=False):
        b = QToolButton()
        b.setDefaultAction(action)  # icon, text, tooltip and enabled state
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setIconSize(QSize(20, 20))
        b.setCursor(Qt.PointingHandCursor)
        if primary:
            b.setObjectName('primary')
        return b

    @staticmethod
    def _nav_button(action):
        """Small, icon-only: these sit inside the diff pane's own header, next
        to the file name, so they read as part of that row rather than as
        another toolbar competing for attention."""
        b = QToolButton()
        b.setDefaultAction(action)
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setIconSize(QSize(14, 14))
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoRaise(True)  # flat until hovered -- no button chrome at rest
        return b

    # --- review: one note and one sign-off per change ---

    def _review_bar(self):
        """Note box for the change under the cursor, plus its Reviewed tick."""
        bar = QFrame()
        bar.setObjectName('reviewbar')
        self.note_edit = _NoteEdit()
        self.note_edit.setFixedHeight(58)
        self.note_edit.setTabChangesFocus(True)
        self.note_edit.left.connect(self._commit_review)
        # a debounce as well as the focus-out: text typed and never left behind
        # (the window closed, the app killed) still reaches the file
        self._note_timer = QTimer(self)
        self._note_timer.setSingleShot(True)
        self._note_timer.setInterval(800)
        self._note_timer.timeout.connect(self._commit_review)
        self.note_edit.textChanged.connect(self._note_timer.start)

        self.cb_reviewed = QCheckBox('Reviewed')
        self.cb_reviewed.setToolTip('Sign this change off. The exported report '
                                    'can then hide it, leaving only what is '
                                    'still to review.')
        self.cb_reviewed.toggled.connect(self._commit_review)
        self.btn_file_reviewed = QToolButton()
        self.btn_file_reviewed.setText('Whole file')
        self.btn_file_reviewed.setCursor(Qt.PointingHandCursor)
        self.btn_file_reviewed.clicked.connect(self._toggle_file_reviewed)
        self.review_where = QLabel('')
        self.review_file = QLabel('')

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(2)
        side.addWidget(self.cb_reviewed)
        side.addWidget(self.btn_file_reviewed)
        side.addWidget(self.review_where)
        side.addWidget(self.review_file)
        side.addStretch(1)

        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(10)
        h.addWidget(self.note_edit, 1)
        h.addLayout(side)
        self._load_review()
        return bar

    def _set_review_mode(self, on):
        """Show or hide the note box. The store is loaded either way -- what is
        already signed off still reaches the exported report, and hiding the
        box never changes a verdict."""
        if not on:
            self._commit_review()  # a note typed and not yet left behind
        self.review_box.setVisible(on)
        # the tree's Review column belongs to the same mode: it is progress
        # bookkeeping, useless while nobody is signing anything off, and it
        # costs a read of every changed file to fill
        self.tree.setColumnHidden(REVIEW_COL, not on)
        if on:
            self._load_review()
            self._refresh_review_column()
            self.note_edit.setFocus()

    def _toggle_reviewed(self):
        # the shortcut works before the mode is on; showing the bar is how the
        # reviewer sees that the tick landed
        self.act_review_mode.setChecked(True)
        if self.cb_reviewed.isEnabled():
            self.cb_reviewed.toggle()  # its toggled signal commits the change

    def _file_state(self):
        """``(rel, units, all_reviewed)`` for the file on screen.

        ``rel`` is None when there is nothing to sign off: a noise-only or
        identical file, a path that could not be compared, or an unreadable
        review file. That is what stops a whole-file tick from claiming
        something nobody could have read."""
        unit = self.diff.current_unit()
        units = self.diff.file_units()
        if unit is None or not units or self._reviews.error:
            return None, [], False
        rel = unit[0]
        return rel, units, all(self._reviews.is_reviewed(rel, u.key) for u in units)

    def _toggle_file_reviewed(self):
        self._commit_review()  # the box may hold a note for one of these units
        rel, units, done = self._file_state()
        if rel is None:
            return
        self.act_review_mode.setChecked(True)
        changed = review.mark_file(self._reviews, rel, units, not done)
        if changed:
            self._save_reviews()
        self._load_review()
        self._refresh_review_column()
        self.statusBar().showMessage(
            '{} change(s) in {} marked {}'.format(
                changed, rel, 'not reviewed' if done else 'reviewed'), 6000)

    def _sync_file_button(self):
        rel, units, done = self._file_state()
        self.btn_file_reviewed.setEnabled(rel is not None)
        self.btn_file_reviewed.setText('Clear file' if done else 'Whole file')
        if rel is None:
            self.btn_file_reviewed.setToolTip('Nothing on this file can be '
                                              'signed off.')
        else:
            self.btn_file_reviewed.setToolTip(
                '{} all {} change(s) in this file (Ctrl+Shift+R). Notes you '
                'wrote are kept.'.format('Un-sign' if done else 'Sign off',
                                         len(units)))

    def _load_reviews(self):
        """Open the review that belongs to this pair of folders. Kept BESIDE
        the NEW folder, not in it: a codegen output folder gets wiped and
        regenerated, and the review has to outlive that."""
        self._review_unit = None
        self._reviews = review.ReviewStore.load(review.default_path(self.new))
        self._load_review()

    def _on_unit_changed(self):
        """The cursor moved to another change (or another file opened). The
        note box still holds the PREVIOUS unit, so write it back before
        loading the new one -- this single seam covers every way the current
        change can move: F7/F8, a click in the diff, a new file, a rescan."""
        self._commit_review()
        self._load_review()

    def _load_review(self):
        unit = self.diff.current_unit()
        self._review_unit = unit
        broken = bool(self._reviews.error)
        editable = unit is not None and not broken
        if broken:
            hint = 'The review file could not be read — editing is off.'
        elif unit is None:
            hint = 'No change to review on this file.'
        else:
            hint = 'Why this change? — purpose, decision, ticket…'
        self.note_edit.setPlaceholderText(hint)
        self.note_edit.setEnabled(editable)
        self.cb_reviewed.setEnabled(editable)
        self.note_edit.blockSignals(True)
        self.cb_reviewed.blockSignals(True)
        if unit:
            rel, key, label = unit
            self.note_edit.setPlainText(self._reviews.note(rel, key))
            self.cb_reviewed.setChecked(self._reviews.is_reviewed(rel, key))
            self.review_where.setText(label)
        else:
            self.note_edit.setPlainText('')
            self.cb_reviewed.setChecked(False)
            self.review_where.setText('')
        self.note_edit.blockSignals(False)
        self.cb_reviewed.blockSignals(False)
        self._sync_file_button()
        self._show_review_file()

    def _show_review_file(self):
        path = self._reviews.path
        if path is None:
            # the stylesheet is set even with nothing to show: this label is
            # red while a review file is broken, and a theme switch that left
            # the old red behind would outlive the state that earned it
            self.review_file.setText('')
            self.review_file.setStyleSheet('color:{}; font-size:11px;'
                                           .format(theme.c('fg-muted')))
            return
        if self._reviews.error:
            self.review_file.setText('⚠ {}'.format(path.name))
            self.review_file.setStyleSheet('color:{}; font-size:11px;'
                                           .format(theme.c('st-err')))
            self.review_file.setToolTip('{}\n\n{}\n\nNothing is loaded from it '
                                        'and nothing will be written over it. '
                                        'Fix or remove the file, then rescan.'
                                        .format(path, self._reviews.error))
        else:
            self.review_file.setText(path.name)
            self.review_file.setStyleSheet('color:{}; font-size:11px;'
                                           .format(theme.c('fg-muted')))
            self.review_file.setToolTip('Notes and sign-offs are saved to\n{}'
                                        .format(path))

    def _commit_review(self):
        """Write what is in the box back to the store, then to disk.

        Nothing is written when the text and the tick already match what is
        stored: the file's timestamp is a signal to whoever shares it, and a
        pass that changed nothing should not move it."""
        self._note_timer.stop()
        unit = self._review_unit
        if unit is None or self._reviews.error:
            return
        rel, key, label = unit
        note = self.note_edit.toPlainText()
        reviewed = self.cb_reviewed.isChecked()
        if (note.strip() == self._reviews.note(rel, key)
                and reviewed == self._reviews.is_reviewed(rel, key)):
            return
        self._reviews.set(rel, key, note, reviewed, label)
        self._save_reviews()
        self._refresh_review_column()  # this file just moved along

    def _save_reviews(self):
        try:
            self._reviews.save()
        except Exception as e:
            # losing the reviewer's own words silently is not acceptable; the
            # in-memory store keeps them for this session either way
            self.statusBar().showMessage(
                'Review NOT saved to {}: {}: {}'.format(
                    self._reviews.path, type(e).__name__, e), 12000)

    def closeEvent(self, event):
        self._commit_review()
        if self._git_temp:
            # checkouts are scratch: they live as long as the session, so
            # flipping between commits is instant, and go with it
            shutil.rmtree(self._git_temp, ignore_errors=True)
            self._git_temp = None
        super().closeEvent(event)


    # --- folder selection ---

    def _pick_folders(self):
        # both sides in one dialog, prefilled: changing only one of them was
        # two native dialogs' worth of clicking, the second of which just
        # re-picked the folder that was already right
        picked = pick_folders(self, self.old, self.new)
        self._front()  # closing a native dialog can leave the window behind others
        if picked is None:
            return
        self.old, self.new = picked
        self._clear_git_old()
        self._start_scan()

    def _front(self):
        """Bring the window back to the front and give it focus."""
        self.raise_()
        self.activateWindow()

    # --- drag & drop: drop the two folders straight onto the window ---

    @staticmethod
    def _dropped_dirs(event):
        return [p for p in (u.toLocalFile() for u in event.mimeData().urls())
                if p and Path(p).is_dir()]

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self._dropped_dirs(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() and self._dropped_dirs(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        dirs = self._dropped_dirs(event)
        if not dirs:
            return
        event.acceptProposedAction()
        if len(dirs) >= 2:
            self.old, self.new = dirs[0], dirs[1]
        elif not self.old or (self.old and self.new):
            # first drop of a pair: OLD, and wait for the second
            self.old, self.new = dirs[0], None
            self.diff.show_drop_hint(self.old)
            self._set_state('idle', 'Ready')
            self._front()
            return
        else:
            self.new = dirs[0]
        self._clear_git_old()
        self._front()
        self._start_scan()

    # --- comparing against a commit ---
    #
    # A commit is not a second kind of compare: it only supplies the OLD
    # folder, checked out read-only to a temp directory. Everything after that
    # -- scan, verdicts, folding, notes, export -- is the ordinary path.

    def _clear_git_old(self):
        """Dropped or picked folders replace a commit as the OLD side."""
        self._old_label = None
        self.diff.set_old_label(None)

    @staticmethod
    def _git_load(folder):
        """``(repo root, subpath, commits)`` for a folder, for the picker.

        Raises :class:`gitsource.GitError` with something the reviewer can act
        on; the dialog prints it inline and stays open, so a wrong folder costs
        one more click instead of a closed window.
        """
        root = gitsource.repo_root(folder)
        if root is None:
            raise gitsource.GitError(
                'Not inside a git checkout: {}\nPick a folder from your '
                'repository, or use Open folders… to compare two folders by '
                'hand.'.format(folder))
        sub = gitsource.rel_in_repo(root, folder)
        return root, sub, gitsource.log(root, sub)

    def _pick_commit(self):
        # the folder lives in the dialog, not out here: reusing whatever was
        # loaded meant the second git compare of a session was stuck on the
        # first one's repository until the app was restarted
        start = self.new if (self.new and gitsource.repo_root(self.new)) else None
        picked = pick_commit(self, start, self._git_load, gitsource.resolve)
        self._front()
        if picked is None:
            return
        folder, root, sub, commit = picked
        self.new = folder
        self._checkout(root, sub, commit)

    def _checkout(self, root, sub, commit):
        if self._git_temp is None:
            self._git_temp = tempfile.mkdtemp(prefix='codegen-compare-git-')
        self._set_state('busy', 'Checking out {}…'.format(commit.short))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()  # let the status chip paint before the wait
        try:
            path = gitsource.export(root, commit.sha, sub, self._git_temp)
        except gitsource.GitError as e:
            # loud: a failed checkout must never fall through to a stale or
            # empty OLD folder and produce a compare that looks finished
            QMessageBox.critical(self, 'Checkout failed', str(e))
            self._set_state('error', 'Checkout failed')
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.old = str(path)
        subject = commit.subject if len(commit.subject) <= 60 else \
            commit.subject[:57] + '…'
        self._old_label = '{}  {}  {}'.format(commit.short, commit.when, subject)
        self.diff.set_old_label(
            '{}  ·  {}'.format(commit.short, subject),
            '{}\n{} — {}\n\nchecked out to {}'.format(
                commit.subject, commit.when, commit.author, path))
        self._start_scan()

    # --- scan lifecycle ---

    # switching a category off changes BOTH places it shows: the file's verdict
    # (status -> Identical/Modified) and how its lines are painted in the diff
    # panes -- greyed out, and dropped from the minimap and from F7/F8. Leaving
    # a wall of red and green in the code after saying those do not count was
    # the worst of both; taking the lines away instead cost the context the
    # remaining changes have to be read in.
    _FOLD_MODE = {'comment-only': 'comment', 'ignorable-only': 'minor'}

    def _fold(self):
        """Change categories the current rules do NOT report separately; those
        files come back Identical (or Modified when real changes remain)."""
        fold = []
        if not self.cb_comment.isChecked():
            fold.append('comment-only')
        if not self.cb_unimportant.isChecked():
            fold.append('ignorable-only')
        return tuple(fold)

    def _start_scan(self):
        if not (self.old and self.new):
            return
        if self.worker and self.worker.isRunning():
            return
        self._commit_review()  # anything typed against the outgoing pair
        self.banner.setVisible(False)
        self.tree.clear()
        self.summary.set_results({})
        self.diff.clear()
        self._raw_results = {}
        self.results = {}
        self._units = {}  # different folders, different content, different keys
        self.act_export.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # busy/indeterminate until first tick
        # the folder NAME, not the two absolute paths: a title bar is not wide
        # enough for a pair of them, and both roots are already named over the
        # diff panes -- with the full path in their tooltip
        name = Path(self.new).name or str(self.new)
        self.setWindowTitle('AUTOSAR CodeGen Compare — {}'.format(name))
        self._load_reviews()
        self.counts_label.setText('')
        self._set_state('busy', 'Scanning…')
        # the scan itself is rule-free; the rules are applied to its results,
        # so flipping a category never costs a second walk of the disk
        self.worker = ScanWorker(self.old, self.new, self.exclude, self.include)
        self.worker.progressed.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_progress(self, done, total, rel):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        # update the state chip itself, not showMessage, so the dot stays lit
        self._set_state('busy', 'Scanning {}/{}: {}'.format(done, total, rel))

    def _on_done(self, results):
        self._raw_results = results
        self._autoselect = True  # consumed by _apply_rules, below
        # the rollup reports the scan itself, never the folded view: a hidden
        # category must not make the model look untouched
        self.summary.set_results(results)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.progress.setVisible(False)
        self.act_export.setEnabled(bool(results))
        errs = sorted(rel for rel, r in results.items() if r['status'] == 'error')
        if errs:
            shown = ', '.join(errs[:20]) + (' …' if len(errs) > 20 else '')
            self.banner.setText('⚠ COMPARE INCOMPLETE — {} path(s) NOT compared '
                                '(treat as potentially changed): {}'.format(len(errs), shown))
            self.banner.setVisible(True)
        self._apply_rules()

    def _apply_rules(self):
        """Re-judge the scanned tree under the current category toggles. Pure
        bookkeeping on results already in memory -- no second walk of the disk,
        so a toggle is instant and the folders are read exactly once."""
        if not self._raw_results:
            return
        keep = self._selected_rel()
        fold = self._fold()
        self.results = apply_fold(self._raw_results, fold)
        self.diff.set_muted_modes([self._FOLD_MODE[f] for f in fold])
        self._refresh_tree()
        self._reselect(keep)  # keep the reviewer on the file they were reading
        if self._autoselect:
            self._autoselect = False
            self._select_first_change()
        counts = summarize(self.results)
        self.counts_label.setText(
            '{real-change} modified · {comment-only} comment-only · '
            '{ignorable-only} unimportant · {added} added · {deleted} deleted · '
            '{identical} identical · {error} error(s)'.format(**counts))
        # a compare with an uncompared path is NOT a clean result: the chip
        # says so in red, matching the banner, so the state is never green when
        # something could be hiding a change
        if counts['error']:
            self._set_state('error', 'Compare incomplete — {} not compared'
                            .format(counts['error']))
        else:
            self._set_state('ready', 'Ready')

    def _on_fail(self, msg):
        self.progress.setVisible(False)
        self.counts_label.setText('')
        self.banner.setText('‼ SCAN FAILED — no results (treat everything as '
                            'potentially changed): {}'.format(msg))
        self.banner.setVisible(True)
        self._set_state('error', 'Scan failed')

    # --- report export ---

    def _export_report(self):
        """Write the same self-contained HTML report the CLI produces.

        Built from the RAW scan, never from the folded view: the report is the
        record of what the compare found, so a category the reviewer collapsed
        on screen (say Comment) must still be in the file, with its real
        verdict. Otherwise an exported report could show a file as Identical
        when it was not -- the silent miss this tool exists to prevent. The
        report's own badges still let the reader hide categories while looking
        at it.

        The review travels with it: every note the reviewer wrote appears next
        to its change, and a Reviewed badge lets the reader fold away what is
        already signed off."""
        if not self._raw_results:
            return
        self._commit_review()  # the box may hold a note never left
        default = str(Path(self.new).parent / default_report_name(self.arxml_only))
        out, _sel = QFileDialog.getSaveFileName(
            self, 'Export HTML report', default, 'HTML report (*.html)')
        self._front()
        if not out:
            return
        try:
            if self.arxml_only:
                # the ARXML/A2L report lists files, not individual changes, so
                # there is nothing for a per-change note to attach to
                page = build_arxml_report(self._raw_results, self.old, self.new,
                                          old_label=self._old_label,
                                          theme_name=self._theme)
            else:
                # only pass the store when it holds something: an untouched
                # review would otherwise add a "0 of N Reviewed" badge to every
                # report, for a feature that run never used
                store = self._reviews if (self._reviews.any_entries()
                                          or self._reviews.error) else None
                # the report opens in whatever the viewer is showing, and
                # carries both palettes so the reader can still switch
                page = build_report(self._raw_results, self.old, self.new, store,
                                    old_label=self._old_label,
                                    theme_name=self._theme)
            Path(out).write_text(page, encoding='utf-8')
        except Exception as e:
            QMessageBox.critical(self, 'Export failed',
                                 '{}: {}'.format(type(e).__name__, e))
            return
        # transient, with a timeout, so the state chip returns after it clears
        self.statusBar().showMessage('Report written (full scan): {}'.format(out), 8000)
        if QMessageBox.question(
                self, 'Report exported',
                'Written to:\n{}\n\nIt contains the full compare, including any '
                'category hidden here.\n\nOpen it now?'.format(out)
                ) == QMessageBox.Yes:
            webbrowser.open(Path(out).resolve().as_uri())
        self._front()

    # --- tree fill + selection ---

    def _refresh_tree(self):
        """Rebuild the tree from results under the current path filter. Cheap
        enough to run on every keystroke; selection is not preserved."""
        self.tree.clear()
        if not self.results:
            return
        self._fill_tree(filter_nodes(
            build_nodes(self.results), text=self.filter_edit.text(),
            hide_identical=self.cb_hide_identical.isChecked()))

    def _refresh_tree_keep_selection(self):
        """Rebuild the tree and put the reviewer back on the file they were
        reading. Toggling a display filter is not a reason to lose the diff on
        screen -- unless that very file is what the filter just hid."""
        keep = self._selected_rel()
        self._refresh_tree()
        self._reselect(keep)

    def _fill_tree(self, nodes):
        def add(parent, node, prefix):
            marker, label, _role = STATUS[node.status]
            item = QTreeWidgetItem(['{}  {}'.format(marker, node.name), label])
            brush = QBrush(QColor(status_color(node.status)))
            item.setForeground(0, brush)
            item.setForeground(1, brush)
            rel = node.rel or (prefix + node.name)
            item.setData(0, PATH_ROLE, rel)  # folders included: the menu opens those too
            if not node.is_dir:
                item.setData(0, REL_ROLE, node.rel)
            for ch in node.children:
                add(item, ch, rel + '/')
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            if node.is_dir:
                item.setExpanded(True)

        for n in nodes:
            add(None, n, '')
        self._refresh_review_column()

    # --- review column: how far along each file is ---

    def _file_units(self, rel):
        """Reviewable units of one file, read from disk once per scan.

        Cached because the column is rebuilt on every keystroke in the filter
        box and after every tick, and re-reading both sides of every changed
        file for that would make the tree crawl. Folding a category cannot
        change the answer: only noise verdicts fold, and those have no units
        either way."""
        if rel not in self._units:
            result = self.results.get(rel)
            self._units[rel] = review.units_of(
                result, Path(self.old) / rel, Path(self.new) / rel) \
                if result and self.old and self.new else []
        return self._units[rel]

    def _refresh_review_column(self):
        """Repaint the Review column from the store. A folder shows the tally
        of everything under it, so a collapsed tree still says where the work
        is left."""
        if self.tree.isColumnHidden(REVIEW_COL):
            return

        def walk(item):
            rel = item.data(0, REL_ROLE)
            if rel is None:  # folder: the sum of what is underneath
                done = total = 0
                for i in range(item.childCount()):
                    d, t = walk(item.child(i))
                    done += d
                    total += t
            else:
                units = self._file_units(rel)
                total = len(units)
                done = sum(1 for u in units
                           if self._reviews.is_reviewed(rel, u.key))
            self._paint_review(item, done, total)
            return done, total

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _paint_review(self, item, done, total):
        state = review_state(done, total)
        if state is None:
            # nothing signable here: an em dash, not a green tick. A noise-only
            # or NOT-compared file has nothing anyone could have read, and a
            # free "done" on it is exactly the false all-clear to avoid.
            item.setText(REVIEW_COL, '—')
            item.setForeground(REVIEW_COL, QBrush(QColor(theme.c('fg-muted'))))
            item.setToolTip(REVIEW_COL, 'Nothing here can be signed off.')
            return
        item.setText(REVIEW_COL, '{}/{}'.format(done, total))
        item.setForeground(REVIEW_COL, QBrush(QColor(review_color(state))))
        item.setToolTip(REVIEW_COL, '{} of {} change(s) reviewed'.format(done, total))

    # --- right-click: open the file where it really lives ---

    def _tree_menu(self, pos):
        menu = self._context_menu(self.tree.itemAt(pos))
        if menu is not None:
            menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _context_menu(self, item):
        """The right-click menu for one tree row, or None when the row has
        nothing to offer. Built apart from showing it so the menu can be
        rendered and looked at without a blocking exec()."""
        if item is None or not (self.old and self.new):
            return None
        rel = item.data(0, PATH_ROLE)
        if not rel:
            return None
        is_file = item.data(0, REL_ROLE) is not None
        # NEW is the folder being reviewed, so it is the only side worth an
        # entry -- except for a deleted path, which exists nowhere else but
        # OLD. Offering both sides everywhere was two clicks' worth of choice
        # for a question that has one answer.
        target = Path(self.new) / rel
        if not target.exists():
            target = Path(self.old) / rel
        menu = QMenu(self)
        menu.setToolTipsVisible(True)  # the tooltip carries the full path
        act = menu.addAction(_SHOW_FILE if is_file else 'Open folder')
        exists = target.exists()
        act.setEnabled(exists)
        act.setToolTip(str(target) if exists else
                       '{}\n\nNot on either side any more.'.format(target))
        act.triggered.connect(
            lambda _checked=False, p=target, s=is_file:
            _open_in_file_manager(p, select=s))
        menu.addSeparator()
        # the FULL path of the same target the entry above opens: a relative
        # path is not something you can paste into a shell, an explorer bar or
        # a ticket, which is what a copied path is for
        full = str(target)
        copy = menu.addAction('Copy full path')
        copy.setToolTip(full)
        copy.triggered.connect(lambda: QApplication.clipboard().setText(full))
        return menu

    def _selected_rel(self):
        items = self.tree.selectedItems()
        return items[0].data(0, REL_ROLE) if items else None

    # --- walking the files, not just the changes inside one ---
    #
    # verdicts a review pass has to look at: everything that is not noise. A
    # finished scan opens on the first of these, and F7/F8 step between them
    # once the current file runs out of changes.
    _NAV_STATUS = ('error', 'real-change', 'added', 'deleted')

    def _tree_rels(self):
        """Every file row, in the order the tree shows it.

        Read from the TREE and not from the results dict on purpose: rows the
        path filter or `Hide identical` took off screen must not be what F8
        jumps to, and the tree is the only thing that knows what is visible.
        """
        out = []

        def walk(item):
            rel = item.data(0, REL_ROLE)
            if rel is not None:
                out.append(rel)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _is_nav(self, rel):
        r = self.results.get(rel)
        return bool(r) and r['status'] in self._NAV_STATUS

    def _select_first_change(self):
        """Open the first file a reviewer would have to read. Called once per
        scan: landing on an empty pane next to a tree full of results makes the
        reviewer's first act a hunt for where the changes are, which the tool
        already knows."""
        rel = next((r for r in self._tree_rels() if self._is_nav(r)), None)
        if rel:
            self._reselect(rel)

    def _step_file(self, delta, to_last=False):
        """Move to the next (delta +1) or previous (-1) file with something to
        review, wrapping round the whole compare. `to_last` parks on that
        file's LAST change, so stepping backwards continues where the eye is."""
        order = self._tree_rels()
        nav = [r for r in order if self._is_nav(r)]
        if not nav:
            return
        cur = self._selected_rel()
        nxt = None
        if cur in order:
            i = order.index(cur)
            after = order[i + 1:] if delta > 0 else list(reversed(order[:i]))
            nxt = next((r for r in after if self._is_nav(r)), None)
        wrapped = nxt is None
        if wrapped:
            nxt = nav[0] if delta > 0 else nav[-1]
        self._reselect(nxt)  # loads the file and parks on its first change
        if to_last:
            self.diff.last_change()
        self.statusBar().showMessage(
            '{}{}'.format('Wrapped to ' if wrapped else '', nxt), 4000)

    def _next_change(self):
        """F8: the next change in this file, or the first change of the next
        file with any. One key walks the whole compare instead of dead-ending
        at the bottom of whichever file happens to be open."""
        if not self.diff.next_change():
            self._step_file(1)

    def _prev_change(self):
        if not self.diff.prev_change():
            self._step_file(-1, to_last=True)

    def _jump_to_name(self, rel, key):
        """Open `rel` from the quick-changes panel, on the hunk about `key`.

        Selecting the tree item loads the file, which parks on its first
        change; the second step moves to the object the clicked row is
        actually about. A row whose name is not in a changed line (a fold is
        hiding it, or the name only occurs in context) leaves the pane on that
        first change rather than scrolling somewhere unrelated.
        """
        self._reselect(rel)
        if key:
            self.diff.goto_name(key)

    def _reselect(self, rel):
        """Re-open the file that was showing before a rescan."""
        if not rel:
            return
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.data(0, REL_ROLE) == rel:
                self.tree.setCurrentItem(item)
                return
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _on_select(self):
        rel = self._selected_rel()
        if rel and rel in self.results:
            self.diff.show_file(rel, self.results[rel], self.old, self.new)


# chrome styling. Deliberately narrow: the diff editors, the minimap and the
# per-file tree colours are painted in code, and a stylesheet rule on their
# items would override those verdict colours. Colours are named as theme roles
# and filled in by apply_theme, so there is one QSS for both schemes.
_QSS = """
QToolBar#main {{ background:{chrome-bg}; border:0; border-bottom:1px solid {border};
                padding:4px 12px 4px 6px; spacing:2px; }}
/* the Help button carries a menu: without room for it the arrow is clipped
   against the window edge */
QToolBar#main QToolButton::menu-indicator {{ subcontrol-position: right center;
                subcontrol-origin: padding; right:-2px; }}
QToolBar#main QToolButton {{ padding:5px 10px; border-radius:6px; color:{icon-tint}; }}
QToolBar#main QToolButton:hover {{ background:{chrome-hover}; }}
QToolBar#main QToolButton:pressed {{ background:{chrome-pressed}; }}
/* Review mode is a MODE: without a lit checked state the button looks the same
   on as off, and the note box appearing is the only clue it worked */
QToolBar#main QToolButton:checked {{ background:{chrome-checked-bg};
                color:{chrome-checked-fg}; }}
QToolBar#main QToolButton:checked:hover {{ background:{chrome-checked-hover}; }}
QFrame#reviewbar {{ background:{chrome-bar-bg}; border-top:1px solid {border}; }}
QFrame#reviewbar QPlainTextEdit {{ background:{code-bg}; border:1px solid {border};
            border-radius:6px; padding:4px 6px; color:{fg}; }}
QFrame#reviewbar QPlainTextEdit:focus {{ border:1px solid {accent-2}; }}
QFrame#reviewbar QPlainTextEdit:disabled {{ background:{chrome-disabled-bg};
            color:{chrome-disabled-fg}; border:1px solid {border}; }}
QToolButton#primary {{ background:{chrome-checked-bg}; color:{chrome-checked-fg}; }}
QToolButton#primary:hover {{ background:{chrome-checked-hover}; }}
QToolButton#primary:disabled {{ background:{chrome-disabled-bg};
            color:{chrome-disabled-fg}; }}
QTreeWidget {{ border:1px solid {border}; border-radius:6px; }}
QTreeWidget::item {{ padding:2px 0; }}
QTreeWidget::item:selected {{ background:{tree-selected}; }}
QHeaderView::section {{ background:{header-bg}; color:{header-fg}; border:0;
                       border-right:1px solid {border}; padding:4px 6px; }}
QLineEdit {{ background:{code-bg}; border:1px solid {border}; border-radius:6px;
            padding:5px 8px; }}
QLineEdit:focus {{ border:1px solid {accent-2}; }}
QSplitter::handle {{ background:{border}; }}
QSplitter::handle:horizontal {{ width:3px; }}
QSplitter::handle:vertical {{ height:3px; }}
QStatusBar {{ background:{chrome-bg}; color:{status-fg}; border-top:1px solid {border}; }}
QProgressBar {{ background:{code-bg}; border:1px solid {border}; border-radius:6px;
               text-align:center; color:{fg}; }}
QProgressBar::chunk {{ background:{progress-chunk}; border-radius:5px; }}
QCheckBox {{ spacing:6px; }}
/* find strip: a band of its own between the header and the code, so it reads
   as a tool over the diff rather than as part of the file being read */
QWidget#findbar {{ background:{chrome-bar-bg}; border-top:1px solid {border};
                  border-bottom:1px solid {border}; }}
QWidget#findbar QToolButton {{ color:{st-ign}; padding:2px 6px; border-radius:4px; }}
QWidget#findbar QToolButton:hover {{ background:{chrome-hover}; color:{fg-strong}; }}
"""


def apply_theme(app):
    """Palette and stylesheet for the whole application, in the current theme.

    Fusion in both directions: the native Windows style ignores most of a
    palette, so a light run under it would come out as a half-themed window
    rather than a light one.
    """
    app.setStyle('Fusion')
    p = QPalette()
    bg, base, text = (QColor(theme.c('bg')), QColor(theme.c('code-bg')),
                      QColor(theme.c('fg')))
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, bg)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Button, base)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.ToolTipBase, base)
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Highlight, QColor(theme.c('tree-selected')))
    p.setColor(QPalette.HighlightedText, QColor(theme.c('fg-strong')))
    # the filter box's "Filter by path…" placeholder: Fusion fades it so far it
    # is barely legible, so set an explicit, readable grey
    p.setColor(QPalette.PlaceholderText, QColor(theme.c('st-ign')))
    app.setPalette(p)
    app.setStyleSheet(_QSS.format(**theme.palette()))


def _taskbar_identity():
    """Windows groups taskbar buttons by AppUserModelID; without our own the
    frozen exe inherits the host python's and shows its icon instead."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'LongVoThien.CodeGenCompareTool')
    except Exception:
        pass  # not Windows, or the call is unavailable: cosmetic either way


def run_viewer(old=None, new=None, exclude=(), arxml_only=False,
               theme_name=theme.DEFAULT):
    app = QApplication.instance()
    owns = app is None
    if owns:
        _taskbar_identity()
        app = QApplication(sys.argv[:1])
    theme.set_current(theme_name)
    apply_theme(app)
    app.setApplicationName('CodeGen Compare')
    app.setWindowIcon(app_icon())
    win = MainWindow(old, new, exclude, arxml_only, theme_name)
    win.show()
    return app.exec() if owns else 0


if __name__ == '__main__':
    sys.exit(run_viewer())
