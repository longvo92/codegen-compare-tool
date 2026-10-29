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

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QSplitter, QStyle, QToolBar,
                               QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, gitsource, theme, zipsource
from ..diff_engine import RULES
from ..main import default_report_name
from ..report import build_arxml_report, render_report, consistency_advisories
from ..scanner import summarize
from .advisories import AdvisoryPanel
from .codecheck import CodeCheckPage
from .dialogs import show_about, show_release_notes, show_user_guide
from .diffpane import DiffPane
from .icons import ACCENT, app_icon, icon, std_icon
from .pickers import pick_commit, pick_folders
from .section import NO_MAX, Section
from .summary import SummaryPanel
from .tree import (STATUS, build_nodes, filter_nodes, move_tooltip,
                   status_color, status_label)
from .worker import ScanWorker

REL_ROLE = Qt.UserRole      # a FILE row's relative path (folders: None)
PATH_ROLE = Qt.UserRole + 1  # relative path of any row, file or folder

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


class MainWindow(QMainWindow):
    def __init__(self, old=None, new=None, exclude=(), arxml_only=False,
                 theme_name=theme.DEFAULT, user_rules=(), skip_var_renames=False):
        super().__init__()
        self._theme = theme.set_current(theme_name)
        self._state = ('idle', 'Ready')
        self.old = old
        self.new = new
        self.exclude = tuple(exclude)
        self.include = _arxml_include() if arxml_only else ()
        self.arxml_only = arxml_only
        # extra --rules noise patterns; the viewer and the CLI share the engine,
        # so both must apply them or the same folders would read two ways
        self.user_rules = tuple(user_rules)
        # --skip-var-renames: the unproven quick check. Baked into the scan
        # like --rules is, because it decides verdicts -- it is not a view
        # toggle the reviewer can flip back on over the same results.
        self.skip_var_renames = bool(skip_var_renames)
        self._raw_results = {}  # verdicts straight from the scan
        self.results = {}       # ... after the current compare rules
        self.worker = None
        # scratch for materialised sources this session: git checkouts and
        # unpacked zips both land here, and go together on close
        self._src_temp = None
        self._old_label = None    # what OLD is, when its folder does not say
        self._new_label = None    # ... and CURRENT, when a zip stands in for it
        # one scan, one automatic jump to the first change. Flipping a compare
        # rule re-judges the same scan and must NOT drag the reviewer off the
        # file they are reading.
        self._autoselect = False

        self.setWindowTitle(APP_NAME + ' — Compare')
        self.setWindowIcon(app_icon())
        self.resize(1200, 800)
        self.setAcceptDrops(True)  # drop the two folders straight onto the window

        self.banner = QLabel()
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['File', 'Status'])
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

        # reading toggles: unticking a category greys its lines out and drops
        # them from the minimap and F7/F8. The VERDICT is left alone -- a
        # comment-only file keeps saying Comment. Re-judging it to Identical is
        # what this used to do, and it made the tree disagree with the exported
        # report about the same file; worse, "Identical" is the one word a
        # reviewer is entitled to read as "nothing differs here at all".
        self.cb_comment = QCheckBox('Comment')
        self.cb_comment.setChecked(True)
        self.cb_comment.setToolTip(
            'Untick to grey out comment-only differences. The file keeps its '
            'Comment verdict; its lines just stop competing for attention and '
            'drop out of F7/F8.')
        self.cb_comment.toggled.connect(self._apply_rules)
        self.cb_unimportant = QCheckBox('Unimportant')
        self.cb_unimportant.setChecked(True)
        self.cb_unimportant.setToolTip(
            'Untick to grey out the other unimportant differences (UUIDs, '
            'timestamps, renames, whitespace). The file keeps its Unimportant '
            'verdict; its lines drop out of F7/F8.')
        self.cb_unimportant.toggled.connect(self._apply_rules)
        # a display filter over the tree, which is why it sits apart from the
        # two above. A regenerated tree is mostly untouched files, and scrolling
        # past hundreds of '=' rows to reach five changed ones is its own way
        # of hiding them.
        self.cb_hide_identical = QCheckBox('Hide identical')
        self.cb_hide_identical.setToolTip(
            'Leave only the files with a difference in the tree. Only genuinely '
            'identical files go: a Comment or Unimportant file stays, greyed or '
            'not. Verdicts, counts and the exported report are unchanged.')
        self.cb_hide_identical.toggled.connect(self._refresh_tree_keep_selection)
        rules = QHBoxLayout()
        rules.setContentsMargins(6, 4, 6, 4)
        rules.addWidget(QLabel('Report:'))
        rules.addWidget(self.cb_comment)
        rules.addWidget(self.cb_unimportant)
        rules.addStretch(1)
        rules.addWidget(self.cb_hide_identical)

        tree_box = QWidget()
        lv = QVBoxLayout(tree_box)
        lv.setContentsMargins(6, 4, 6, 0)
        lv.setSpacing(4)
        lv.addLayout(rules)
        lv.addWidget(self.filter_edit)
        lv.addWidget(self.tree, 1)

        # quick-changes rollup under the tree: the same "what changed in the
        # model / calibration" view --arxml-only gives, without leaving the app
        self.summary = SummaryPanel()
        self.summary.fileActivated.connect(self._jump_to_name)

        # cross-artifact / cross-model heads-up, last in the column -- the same
        # list the report and the CLI print, read from the raw scan.
        self.advisories = AdvisoryPanel()

        # all three panes are collapsible and all three are in ONE splitter, so
        # every one of them can be dragged to the height the reviewer wants.
        # The advisories used to sit outside it, pinned: the one pane whose
        # length is least predictable (a folder full of stale models) was the
        # one that could not be resized.
        self.sec_files = Section('FILES', tree_box)
        self.sec_changes = Section('QUICK CHANGES', self.summary)
        self.sec_consistency = Section('REGENERATION ADVISORIES', self.advisories)
        self._sections = (self.sec_files, self.sec_changes,
                          self.sec_consistency)

        # remembered height per pane, so folding one and opening it again
        # puts it back where the reviewer had it
        self._sec_height = {}
        left = QSplitter(Qt.Vertical)
        for sec in self._sections:
            left.addWidget(sec)
            sec.toggled.connect(
                lambda expanded, s=sec: self._on_section_toggled(s, expanded))
        # a folded pane must not be draggable back open by the handle alone --
        # the header is the way in, and a stray drag would leave a sliver of a
        # pane the reviewer explicitly folded
        for i in range(left.count()):
            left.setCollapsible(i, False)
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 1)
        left.setStretchFactor(2, 0)
        self.left_split = left
        # nothing to say yet: the consistency pane starts folded, and stays out
        # of the way until a scan gives it something
        self.sec_consistency.set_expanded(False)
        self.sec_consistency.setVisible(False)
        left.setSizes([560, 240, 0])

        left_col = QWidget()
        lc = QVBoxLayout(left_col)
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(0)
        lc.addWidget(left, 1)
        self._left_layout = lc

        self.diff = DiffPane()

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left_col)
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
        self.modes = QTabWidget()
        self.modes.setObjectName('workspaces')
        self.modes.tabBar().setObjectName('workspaceModes')
        self.compare_page = central
        self.modes.addTab(central, 'Compare')
        self.code_check = CodeCheckPage(lambda: self.new, self)
        self.modes.addTab(self.code_check, 'Code Check')
        self.setCentralWidget(self.modes)

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
        self.modes.currentChanged.connect(self._switch_workspace)
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

    def _switch_workspace(self, index):
        comparing = index == 0
        for action in self._compare_toolbar_actions:
            action.setVisible(comparing)
        for action in (self.act_first, self.act_prev, self.act_next, self.act_last):
            action.setEnabled(comparing)
        self.act_export.setEnabled(comparing and bool(self._raw_results))
        self.statusBar().setVisible(comparing)
        self.code_check.refresh_current()
        if comparing:
            self.setWindowTitle(getattr(self, '_compare_title', APP_NAME + ' — Compare'))
        else:
            self._compare_title = self.windowTitle()
            self.setWindowTitle(APP_NAME + ' — Code Check')

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
            self.advisories.apply_theme()
            self.code_check.apply_theme()
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

        # text and a sun/moon glyph, no shipped icon: the label names where the
        # click GOES, and reusing another button's glyph for it would make two
        # different commands look like the same one
        self.act_theme = QAction(self._theme_label(), self)
        self.act_theme.setCheckable(True)
        self.act_theme.setChecked(self._theme == theme.LIGHT)
        self.act_theme.setToolTip('Switch the viewer between the dark and the '
                                  'light colour scheme')
        self.act_theme.triggered.connect(self._toggle_theme)

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
                    self.act_last, self.act_export):
            self.addAction(act)

    def _build_toolbar(self):
        tb = QToolBar('Compare', self.compare_page)
        self.compare_toolbar = tb
        self.compare_page.layout().insertWidget(0, tb)
        tb.setObjectName('main')
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addAction(self.act_open)
        tb.addAction(self.act_git)
        tb.addWidget(self._tool_button(self.act_export, primary=True))
        self._compare_toolbar_actions = list(tb.actions())
        tb = QToolBar('Application', self.modes)
        tb.setObjectName('global')
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.modes.setCornerWidget(tb, Qt.TopRightCorner)
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

    def closeEvent(self, event):
        running = [w for w in (self.worker, self.code_check.worker) if w and w.isRunning()]
        if running:
            # Keep source directories and QThreads alive until their reads finish.
            event.ignore()
            if not getattr(self, '_close_pending', False):
                self._close_pending = True
                self.setEnabled(False)
                for worker in running:
                    worker.finished.connect(self.close)
            return
        self.code_check.cleanup()
        if self._src_temp:
            # checkouts and unpacked zips are scratch: they live as long as the
            # session, so flipping between sources is instant, and go with it
            shutil.rmtree(self._src_temp, ignore_errors=True)
            self._src_temp = None
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
        old, new = picked
        # a side may be a .zip typed or browsed to: _use_source unpacks it and
        # labels the side, or clears the label for a plain folder
        if not (self._use_source('old', old) and self._use_source('new', new)):
            return
        self._start_scan()

    def _front(self):
        """Bring the window back to the front and give it focus."""
        self.raise_()
        self.activateWindow()

    # --- drag & drop: drop the two folders (or .zip artifacts) onto the window ---

    @staticmethod
    def _droppable(event):
        """Dropped paths that can be a compare source: a folder, or a zip."""
        return [p for p in (u.toLocalFile() for u in event.mimeData().urls())
                if p and (Path(p).is_dir() or zipsource.is_zip(p))]

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self._droppable(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() and self._droppable(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = self._droppable(event)
        if not paths:
            return
        event.acceptProposedAction()
        if self.modes.currentWidget() is self.code_check:
            if not self.code_check.is_running():
                self.code_check.source.setText(paths[0])
            self._front()
            return
        if len(paths) >= 2:
            if not (self._use_source('old', paths[0])
                    and self._use_source('new', paths[1])):
                return  # a zip failed to open; the message said why
        elif not self.old or (self.old and self.new):
            # first drop of a pair: OLD, and wait for the second
            if not self._use_source('old', paths[0]):
                return
            self.new = None
            self.diff.set_new_label(None)
            self._new_label = None
            self.diff.show_drop_hint(self.old)
            self._set_state('idle', 'Ready')
            self._front()
            return
        elif not self._use_source('new', paths[0]):
            return
        self._front()
        self._start_scan()

    # --- comparing against a commit or a zip ---
    #
    # Neither is a second kind of compare: a commit or a zip only supplies one
    # of the two folders, materialised read-only into a temp directory.
    # Everything after that -- scan, verdicts, folding, notes, export -- is the
    # ordinary path, none the wiser where the folder came from.

    def _extract_zip(self, path):
        """Unpack a dropped zip into the session temp, busy cursor up. Returns
        the content folder, or None (with a message shown) when it will not
        open -- loud, never a silent empty folder that reads as a clean
        compare."""
        if self._src_temp is None:
            self._src_temp = tempfile.mkdtemp(prefix='codegen-compare-src-')
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()  # let the cursor change before the unzip
        try:
            return str(zipsource.extract(path, self._src_temp))
        except zipsource.ZipError as e:
            QMessageBox.critical(self, 'Zip could not be opened', str(e))
            return None
        finally:
            QApplication.restoreOverrideCursor()

    def _use_source(self, side, path):
        """Assign ``path`` -- a folder or a ``.zip`` -- to 'old' or 'new'. A zip
        is unpacked and the side labelled by its file name (the temp path names
        nothing); a folder clears any label. False when a zip failed to open."""
        if zipsource.is_zip(path):
            folder = self._extract_zip(path)
            if folder is None:
                return False
            label, tip = Path(path).name, str(path)
        else:
            folder, label, tip = str(path), None, None
        if side == 'old':
            self.old, self._old_label = folder, label
            self.diff.set_old_label(label, tip)
        else:
            self.new, self._new_label = folder, label
            self.diff.set_new_label(label, tip)
        return True

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
        if self._src_temp is None:
            self._src_temp = tempfile.mkdtemp(prefix='codegen-compare-src-')
        self._set_state('busy', 'Checking out {}…'.format(commit.short))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()  # let the status chip paint before the wait
        try:
            path = gitsource.export(root, commit.sha, sub, self._src_temp)
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

    # switching a category off changes how its lines are PAINTED -- greyed
    # out, and dropped from the minimap and from F7/F8 -- and nothing else.
    # Leaving a wall of red and green in the code after saying those do not
    # count was the worst of both; taking the lines away instead cost the
    # context the remaining changes have to be read in. The verdict is not
    # part of it: a file the reviewer greyed out still differs, and the tree
    # has to keep saying so.
    _MUTE_MODE = {'comment-only': 'comment', 'ignorable-only': 'minor'}

    def _muted_statuses(self):
        """Verdicts whose lines the reviewer has switched off. They are played
        down in the panes, never re-judged."""
        muted = []
        if not self.cb_comment.isChecked():
            muted.append('comment-only')
        if not self.cb_unimportant.isChecked():
            muted.append('ignorable-only')
        return tuple(muted)

    def _start_scan(self):
        if not (self.old and self.new):
            return
        if self.worker and self.worker.isRunning():
            return
        self.banner.setVisible(False)
        self.tree.clear()
        self.summary.set_results({})
        self._show_advisories(())
        self.diff.clear()
        self._raw_results = {}
        self.results = {}
        self.act_export.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # busy/indeterminate until first tick
        # the folder NAME, not the two absolute paths: a title bar is not wide
        # enough for a pair of them, and both roots are already named over the
        # diff panes -- with the full path in their tooltip
        name = Path(self.new).name or str(self.new)
        # the quick check rides in the title because it has no undo inside this
        # window: it changed what the scan judged, so the reviewer has to see
        # which mode produced the tree they are reading
        quick = ' — QUICK CHECK: variable renames skipped' if self.skip_var_renames else ''
        self._compare_title = '{} — Compare — {}{}'.format(APP_NAME, name, quick)
        if self.modes.currentIndex() == 0:
            self.setWindowTitle(self._compare_title)
        self.counts_label.setText('')
        self._set_state('busy', 'Scanning…')
        # the scan itself is rule-free; the rules are applied to its results,
        # so flipping a category never costs a second walk of the disk
        self.worker = ScanWorker(self.old, self.new, self.exclude, self.include,
                                 self.user_rules, self.skip_var_renames)
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
        # same rule for the advisories: read from the raw scan, so a collapsed
        # category can never hide a desync heads-up
        self._show_advisories(consistency_advisories(results))
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.progress.setVisible(False)
        self.act_export.setEnabled(bool(results) and self.modes.currentIndex() == 0)
        errs = sorted(rel for rel, r in results.items() if r['status'] == 'error')
        if errs:
            shown = ', '.join(errs[:20]) + (' …' if len(errs) > 20 else '')
            self.banner.setText('⚠ COMPARE INCOMPLETE — {} path(s) NOT compared '
                                '(treat as potentially changed): {}'.format(len(errs), shown))
            self.banner.setVisible(True)
        self._apply_rules()

    def _apply_rules(self):
        """Re-paint the scanned tree under the current category toggles. Pure
        bookkeeping on results already in memory -- no second walk of the disk,
        so a toggle is instant and the folders are read exactly once.

        The results themselves are the raw scan: a toggle decides what is
        greyed, never what a file's verdict is."""
        if not self._raw_results:
            return
        keep = self._selected_rel()
        muted = self._muted_statuses()
        self.results = dict(self._raw_results)
        self.diff.set_muted_modes([self._MUTE_MODE[s] for s in muted])
        self._refresh_tree()
        self._reselect(keep)  # keep the reviewer on the file they were reading
        if self._autoselect:
            self._autoselect = False
            self._select_first_change()
        counts = summarize(self.results)
        # the verdict words are spelled the way the tree's Status column and
        # the report's badges spell them -- one state, one name, whichever
        # surface the reviewer is reading
        errors = '{} {}'.format(counts['error'],
                                'Error' if counts['error'] == 1 else 'Errors')
        self.counts_label.setText(
            '{real-change} Modified · {comment-only} Comment · '
            '{ignorable-only} Unimportant · {added} Added · {deleted} Deleted · '
            '{identical} Identical · {errors}'.format(errors=errors, **counts))
        # a compare with an uncompared path is NOT a clean result: the chip
        # says so in red, matching the banner, so the state is never green when
        # something could be hiding a change
        if counts['error']:
            self._set_state('error', 'Compare incomplete — {} not compared'
                            .format(counts['error']))
        else:
            self._set_state('ready', 'Ready')

    # a pane never re-opens at whatever height is left over: the reviewer
    # dragged it to a size once, and folding it away to read something else is
    # not them changing their mind about that size
    _SEC_MIN = 90

    def _on_section_toggled(self, sec, expanded):
        """Fold: hand that pane's height to the panes still open. Unfold: take
        it back from them, in proportion to what each has to spare."""
        sizes = self.left_split.sizes()
        if len(sizes) != len(self._sections):
            return
        i = self._sections.index(sec)
        bar = sec.header_height()
        # remember the height FIRST: folding the last open pane returns early
        # below, and skipping this there lost the size -- reopening some other
        # pane and coming back to this one then landed on the default
        if not expanded:
            self._sec_height[sec] = max(sizes[i], self._SEC_MIN)
        others = [n for n, s in enumerate(self._sections)
                  if n != i and s.is_expanded() and s.isVisible()]
        if not others:
            self._park_column()      # last pane folded: stack them at the top
            return
        if not expanded:
            self._spread(sizes, sizes[i] - bar, others)
            sizes[i] = bar
        else:
            want = max(self._sec_height.get(sec, 200), self._SEC_MIN)
            got = self._spread(sizes, -(want - sizes[i]), others)
            sizes[i] += -got
        self.left_split.setSizes(sizes)
        self._park_column()

    def _spread(self, sizes, amount, idx):
        """Add `amount` px across `idx` (negative takes away). Returns what was
        actually moved -- a pane is never squeezed below _SEC_MIN, so asking
        for more than the column has spare gives back less than was asked."""
        if amount >= 0:
            share, rest = divmod(amount, len(idx))
            for n, i in enumerate(idx):
                sizes[i] += share + (rest if n == 0 else 0)
            return amount
        spare = [max(0, sizes[i] - self._SEC_MIN) for i in idx]
        take = min(-amount, sum(spare))
        left = take
        for n, i in enumerate(idx):
            cut = min(spare[n], left)
            sizes[i] -= cut
            left -= cut
        return -(take - left)

    def _park_column(self):
        """With every pane folded the splitter is shorter than the column it
        sits in. Left alone, Qt centres it and the bars end up adrift halfway
        down an empty panel; capped and top-aligned they stack under the
        toolbar, which is where a row of collapsed headers belongs."""
        shown = [s for s in self._sections if s.isVisible()]
        if any(s.is_expanded() for s in shown):
            self._left_layout.setAlignment(self.left_split, Qt.Alignment(0))
            self.left_split.setMaximumHeight(NO_MAX)
            return
        bars = sum(s.header_height() for s in shown)
        handles = self.left_split.handleWidth() * max(0, len(shown) - 1)
        self.left_split.setMaximumHeight(bars + handles)
        self._left_layout.setAlignment(self.left_split, Qt.AlignTop)

    def _resize_sections(self):
        """Re-cap every folded pane at its bar. Used after the panes change on
        their own -- a scan revealing the consistency pane, say."""
        sizes = self.left_split.sizes()
        if len(sizes) != len(self._sections):
            return
        freed = 0
        for i, sec in enumerate(self._sections):
            if not sec.is_expanded():
                bar = sec.header_height()
                freed += max(0, sizes[i] - bar)
                sizes[i] = bar
        open_idx = [i for i, s in enumerate(self._sections)
                    if s.is_expanded() and s.isVisible()]
        if freed and open_idx:
            self._spread(sizes, freed, open_idx)
        elif not open_idx:
            self.left_split.setSizes(sizes)
            self._park_column()
            return
        self.left_split.setSizes(sizes)
        self._park_column()

    def _show_advisories(self, advisories):
        """Fill the consistency pane and open it only when it has something to
        say. A clean compare spends no height on it, and a reviewer who folded
        it stays folded -- reopening a pane someone shut is the tool arguing
        with them."""
        self.advisories.set_advisories(advisories)
        # AdvisoryPanel hides itself when empty; inside a section the SECTION is
        # what has to go, or an empty bar is left behind
        had = self.sec_consistency.isVisible()
        n = len(advisories)
        self.sec_consistency.setVisible(bool(n))
        self.sec_consistency.set_suffix(
            '{} heads-up{}'.format(n, '' if n == 1 else 's') if n else '')
        if n and not had:
            self.sec_consistency.set_expanded(True)
            sizes = self.left_split.sizes()
            want = min(140, max(80, 28 * n + 34))
            if len(sizes) == 3 and sizes[2] < want:
                take = want - sizes[2]
                sizes[2] = want
                sizes[0] = max(120, sizes[0] - take)
                self.left_split.setSizes(sizes)
        self._resize_sections()

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
        """
        if not self._raw_results:
            return
        default = str(Path(self.new).parent / default_report_name(self.arxml_only))
        out, _sel = QFileDialog.getSaveFileName(
            self, 'Export HTML report', default, 'HTML report (*.html)')
        self._front()
        if not out:
            return
        try:
            if self.arxml_only:
                page = build_arxml_report(self._raw_results, self.old, self.new,
                                          old_label=self._old_label,
                                          new_label=self._new_label,
                                          theme_name=self._theme)
            else:
                # the report opens in whatever the viewer is showing, and
                # carries both palettes so the reader can still switch
                rendered = render_report(self._raw_results, self.old, self.new,
                                    old_label=self._old_label,
                                    new_label=self._new_label,
                                    theme_name=self._theme)
                page = rendered.html
            Path(out).write_text(page, encoding='utf-8')
            if not self.arxml_only and rendered.diagnostics:
                QMessageBox.warning(self, 'Report incomplete', '\n'.join(rendered.diagnostics))
                return
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
            marker, _label, _role = STATUS[node.status]
            item = QTreeWidgetItem(['{}  {}'.format(marker, node.name),
                                    status_label(node)])
            brush = QBrush(QColor(status_color(node.status)))
            item.setForeground(0, brush)
            item.setForeground(1, brush)
            tip = move_tooltip(node)
            if tip:
                # the path it came from does not fit the column, and a file
                # that moved is exactly the row somebody wants the detail on
                item.setToolTip(0, tip)
                item.setToolTip(1, tip)
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
    #
    # comment-only / ignorable-only are noise verdicts, but they are walkable
    # while their checkbox is ticked, so a reviewer can step through
    # everything. _is_nav drops them again the moment the box is unticked:
    # those rows are greyed and off the minimap, so there is nothing in such a
    # file for F7/F8 to stop on, and stepping into it would dead-end.
    _NAV_STATUS = ('error', 'real-change', 'added', 'deleted',
                   'comment-only', 'ignorable-only')

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
        if not r:
            return False
        # a greyed-out category has no stops left in it
        if r['status'] in self._muted_statuses():
            return False
        return r['status'] in self._NAV_STATUS

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
QTabBar#workspaceModes::tab {{ padding:10px 28px; font-size:13px;
                             font-weight:600; color:{fg-dim}; background:{chrome-bg}; }}
QTabBar#workspaceModes::tab:selected {{ color:{fg-strong}; background:{panel-3};
                                      border-bottom:3px solid {accent-2}; }}
QTabWidget#workspaces::pane {{ border:0; border-top:1px solid {border}; }}
QToolBar {{ background:{chrome-bg}; border:0; border-bottom:1px solid {border};
                padding:4px 12px 4px 6px; spacing:2px; }}
/* the Help button carries a menu: without room for it the arrow is clipped
   against the window edge */
QToolBar QToolButton::menu-indicator {{ subcontrol-position: right center;
                subcontrol-origin: padding; right:-2px; }}
QToolBar QToolButton {{ padding:5px 10px; border-radius:6px; color:{icon-tint}; }}
QToolBar QToolButton:hover {{ background:{chrome-hover}; }}
QToolBar QToolButton:pressed {{ background:{chrome-pressed}; }}
QToolBar QToolButton:checked {{ background:{chrome-checked-bg};
                color:{chrome-checked-fg}; }}
QToolBar QToolButton:checked:hover {{ background:{chrome-checked-hover}; }}
/* left-column section bars. Small, flat and quiet: a bar the eye skips over
   until it is looking for one, the way an editor sidebar names its panes. The
   arrow lives in the label (see section.py) so no icon theme is needed. */
QPushButton#sectionhead {{ background:{chrome-bar-bg}; color:{header-fg};
            border:none; border-top:1px solid {border}; padding:5px 8px;
            font-size:11px; font-weight:bold; text-align:left; }}
QPushButton#sectionhead:hover {{ background:{chrome-hover}; color:{fg-strong}; }}
QPushButton#sectionhead:focus {{ outline:none; }}
/* consistency heads-up at the bottom of the left column: a band of its own,
   set off from the quick-changes rollup above it by a top border */
QFrame#advisorypanel {{ background:{chrome-bar-bg}; }}
/* the scroll area AND its viewport: the viewport is a child widget that fills
   itself with the Base colour, which paints a lighter block under the header
   instead of letting the band show through */
QFrame#advisorypanel QScrollArea,
QFrame#advisorypanel QScrollArea > QWidget > QWidget {{ background:transparent; }}
QLabel#advisoryhead {{ font-size:12px; }}
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
/* thin, rounded, arrow-less scrollbars -- the chunky Fusion default reads as a
   second UI panel beside the code; this one recedes until hovered */
QScrollBar:vertical {{ background:transparent; width:12px; margin:0; }}
QScrollBar:horizontal {{ background:transparent; height:12px; margin:0; }}
QScrollBar::handle:vertical {{ background:{scroll-thumb}; min-height:32px;
            border-radius:5px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:{scroll-thumb}; min-width:32px;
            border-radius:5px; margin:2px; }}
QScrollBar::handle:hover {{ background:{scroll-thumb-hover}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QAbstractScrollArea::corner {{ background:transparent; }}
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
            'LongVoThien.CodeGenInspector')
    except Exception:
        pass  # not Windows, or the call is unavailable: cosmetic either way


def run_viewer(old=None, new=None, exclude=(), arxml_only=False,
               theme_name=theme.DEFAULT, user_rules=(), skip_var_renames=False):
    app = QApplication.instance()
    owns = app is None
    if owns:
        _taskbar_identity()
        app = QApplication(sys.argv[:1])
    theme.set_current(theme_name)
    apply_theme(app)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    win = MainWindow(old, new, exclude, arxml_only, theme_name, user_rules,
                     skip_var_renames)
    win.show()
    return app.exec() if owns else 0


if __name__ == '__main__':
    sys.exit(run_viewer())
