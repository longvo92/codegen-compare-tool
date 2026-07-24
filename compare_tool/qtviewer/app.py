"""Viewer main window: folder tree on the left, diff pane on the right.

The scan runs on a :class:`ScanWorker` thread; the window only reacts to its
signals. Fail-safe stays first-class: a worker crash or any uncompared path
raises a loud red banner -- an incomplete compare must never look clean.
"""

import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QProgressBar,
                               QSizePolicy, QSplitter, QStyle, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..diff_engine import RULES
from ..main import default_report_name
from ..report import build_arxml_report, build_report
from ..scanner import apply_fold, summarize
from .dialogs import show_about, show_release_notes, show_user_guide
from .diffpane import DiffPane
from .icons import ACCENT, app_icon, icon, std_icon
from .summary import SummaryPanel
from .tree import STATUS, build_nodes, filter_nodes
from .worker import ScanWorker

REL_ROLE = Qt.UserRole  # QTreeWidgetItem data slot holding a file's rel path


def _arxml_include():
    """Same include globs run_compare uses for --arxml-only."""
    return tuple('*' + ext for ext, rs in RULES.items() if rs in ('arxml', 'a2l'))


class MainWindow(QMainWindow):
    def __init__(self, old=None, new=None, exclude=(), arxml_only=False):
        super().__init__()
        self.old = old
        self.new = new
        self.exclude = tuple(exclude)
        self.include = _arxml_include() if arxml_only else ()
        self.arxml_only = arxml_only
        self._raw_results = {}  # verdicts straight from the scan
        self.results = {}       # ... after the current compare rules
        self.worker = None

        self.setWindowTitle('AUTOSAR CodeGen Compare — viewer')
        self.setWindowIcon(app_icon())
        self.resize(1200, 800)
        self.setAcceptDrops(True)  # drop the two folders straight onto the window

        self.banner = QLabel()
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet('background:#4a1d1d; color:#ffd6d6; padding:6px 10px;'
                                  'font-weight:bold; border-bottom:1px solid #b04a4a;')

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['File', 'Status'])
        self.tree.setUniformRowHeights(True)
        # the name column hugs its content instead of taking a fixed 380 px,
        # so Status sits right next to the file name and never gets pushed out
        # of the panel
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self._on_select)

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
        rules = QHBoxLayout()
        rules.setContentsMargins(0, 0, 0, 0)
        rules.addWidget(QLabel('Report:'))
        rules.addWidget(self.cb_comment)
        rules.addWidget(self.cb_unimportant)
        rules.addStretch(1)

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
        self.summary.fileActivated.connect(self._reselect)
        left = QSplitter(Qt.Vertical)
        left.addWidget(tree_box)
        left.addWidget(self.summary)
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 1)
        left.setSizes([560, 240])

        self.diff = DiffPane()

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
        # navigation and export live on a bar at the BOTTOM, next to the diff
        # they act on -- the toolbar up top is for opening folders and help
        v.addWidget(self._action_bar())
        self.setCentralWidget(central)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(240)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)

        self._build_toolbar()

        if self.old and self.new:
            self._start_scan()
        else:
            # no folders yet: invite a drag & drop instead of forcing a modal
            # file dialog on the reviewer the moment the app opens. One folder
            # on the command line counts as OLD and waits for its NEW.
            self.diff.show_drop_hint(self.old)
            self.statusBar().showMessage(
                'Drop the NEW folder onto this window.' if self.old else
                'Drag the OLD and NEW folders onto this window, or use '
                '"Open folders…".')

    # --- actions, toolbar, bottom action bar ---

    def _make_actions(self):
        """Every command the window offers, in one place. The bottom bar and
        the toolbar are just two views of these actions, so a button and its
        shortcut can never drift apart."""
        self.act_open = QAction(std_icon(self, QStyle.SP_DirOpenIcon),
                                'Open folders…', self)
        self.act_open.setToolTip('Choose the OLD and NEW folders — or drop them '
                                 'straight onto the window')
        self.act_open.triggered.connect(self._pick_folders)

        nav = (('act_first', 'nav-first-change', 'First change', 'Ctrl+Home',
                self._first_change),
               ('act_prev', 'nav-prev-change', 'Previous change', 'F7',
                self._prev_change),
               ('act_next', 'nav-next-change', 'Next change', 'F8',
                self._next_change),
               ('act_last', 'nav-last-change', 'Last change', 'Ctrl+End',
                self._last_change))
        for attr, glyph, text, key, slot in nav:
            act = QAction(icon(glyph), text, self)
            act.setShortcut(key)
            act.setToolTip('{} ({}) — noise is skipped'.format(text, key))
            act.triggered.connect(slot)
            setattr(self, attr, act)

        self.act_export = QAction(icon('export', ACCENT), 'Export report…', self)
        self.act_export.setShortcut('Ctrl+E')
        self.act_export.setEnabled(False)
        self.act_export.setToolTip('Write the full HTML report (Ctrl+E) — always '
                                   'the complete scan, never the folded view')
        self.act_export.triggered.connect(self._export_report)

        self.act_guide = QAction(icon('report'), 'User guide', self)
        self.act_guide.setShortcut('F1')
        self.act_guide.setToolTip('How to use the viewer (F1)')
        self.act_guide.triggered.connect(lambda: show_user_guide(self))

        self.act_notes = QAction(icon('review-resolved'), 'Release notes', self)
        self.act_notes.setToolTip("What changed in this and earlier versions")
        self.act_notes.triggered.connect(lambda: show_release_notes(self))

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
        tb = self.addToolBar('main')
        tb.setObjectName('main')
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addAction(self.act_open)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)  # help actions sit on the right, away from Open
        tb.addAction(self.act_guide)
        tb.addAction(self.act_notes)
        tb.addAction(self.act_about)

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

    def _action_bar(self):
        bar = QFrame()
        bar.setObjectName('actionbar')
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 5, 8, 5)
        h.setSpacing(4)
        for act in (self.act_first, self.act_prev, self.act_next, self.act_last):
            h.addWidget(self._tool_button(act))
        self.pos_label = QLabel('')
        self.pos_label.setStyleSheet('color:#9a9a9a; padding:0 10px;')
        h.addWidget(self.pos_label)
        h.addStretch(1)
        h.addWidget(self._tool_button(self.act_export, primary=True))
        return bar

    # navigation goes through the window so the position readout stays in step
    def _first_change(self):
        self.diff.first_change()
        self._sync_position()

    def _prev_change(self):
        self.diff.prev_change()
        self._sync_position()

    def _next_change(self):
        self.diff.next_change()
        self._sync_position()

    def _last_change(self):
        self.diff.last_change()
        self._sync_position()

    def _sync_position(self):
        self.pos_label.setText(self.diff.position_text())

    # --- folder selection ---

    def _pick_folders(self):
        o = QFileDialog.getExistingDirectory(self, 'Select OLD folder', self.old or '')
        if not o:
            self._front()
            return
        n = QFileDialog.getExistingDirectory(self, 'Select NEW folder', self.new or o)
        self._front()  # closing a native dialog can leave the window behind others
        if not n:
            return
        self.old, self.new = o, n
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
            self.statusBar().showMessage(
                'OLD = {} — now drop the NEW folder.'.format(self.old))
            self._front()
            return
        else:
            self.new = dirs[0]
        self._front()
        self._start_scan()

    # --- scan lifecycle ---

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
        self.banner.setVisible(False)
        self.tree.clear()
        self.summary.set_results({})
        self.diff.clear()
        self.pos_label.setText('')
        self._raw_results = {}
        self.results = {}
        self.act_export.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # busy/indeterminate until first tick
        self.setWindowTitle('AUTOSAR CodeGen Compare — {}  →  {}'.format(self.old, self.new))
        self.statusBar().showMessage('Scanning…')
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
        self.statusBar().showMessage('Scanning {}/{}: {}'.format(done, total, rel))

    def _on_done(self, results):
        self._raw_results = results
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
        self.results = apply_fold(self._raw_results, self._fold())
        self._refresh_tree()
        self._reselect(keep)  # keep the reviewer on the file they were reading
        counts = summarize(self.results)
        self.statusBar().showMessage(
            '{real-change} modified · {comment-only} comment-only · '
            '{ignorable-only} unimportant · {added} added · {deleted} deleted · '
            '{identical} identical · {error} error(s)'.format(**counts))

    def _on_fail(self, msg):
        self.progress.setVisible(False)
        self.banner.setText('‼ SCAN FAILED — no results (treat everything as '
                            'potentially changed): {}'.format(msg))
        self.banner.setVisible(True)
        self.statusBar().showMessage('SCAN FAILED')

    # --- report export ---

    def _export_report(self):
        """Write the same self-contained HTML report the CLI produces.

        Built from the RAW scan, never from the folded view: the report is the
        record of what the compare found, so a category the reviewer collapsed
        on screen (say Comment) must still be in the file, with its real
        verdict. Otherwise an exported report could show a file as Identical
        when it was not -- the silent miss this tool exists to prevent. The
        report's own badges still let the reader hide categories while looking
        at it."""
        if not self._raw_results:
            return
        default = str(Path(self.new).parent / default_report_name(self.arxml_only))
        out, _sel = QFileDialog.getSaveFileName(
            self, 'Export HTML report', default, 'HTML report (*.html)')
        self._front()
        if not out:
            return
        try:
            build = build_arxml_report if self.arxml_only else build_report
            Path(out).write_text(build(self._raw_results, self.old, self.new),
                                 encoding='utf-8')
        except Exception as e:
            QMessageBox.critical(self, 'Export failed',
                                 '{}: {}'.format(type(e).__name__, e))
            return
        self.statusBar().showMessage('Report written (full scan): {}'.format(out))
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
        self._fill_tree(filter_nodes(build_nodes(self.results),
                                     text=self.filter_edit.text()))

    def _fill_tree(self, nodes):
        def add(parent, node):
            marker, label, color = STATUS[node.status]
            item = QTreeWidgetItem(['{}  {}'.format(marker, node.name), label])
            brush = QBrush(QColor(color))
            item.setForeground(0, brush)
            item.setForeground(1, brush)
            if not node.is_dir:
                item.setData(0, REL_ROLE, node.rel)
            for ch in node.children:
                add(item, ch)
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            if node.is_dir:
                item.setExpanded(True)

        for n in nodes:
            add(None, n)

    def _selected_rel(self):
        items = self.tree.selectedItems()
        return items[0].data(0, REL_ROLE) if items else None

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
            self._sync_position()


# chrome styling. Deliberately narrow: the diff editors, the minimap and the
# per-file tree colours are painted in code, and a stylesheet rule on their
# items would override those verdict colours.
_QSS = """
QToolBar#main { background:#25262a; border:0; border-bottom:1px solid #34363c;
                padding:4px 6px; spacing:2px; }
QToolBar#main QToolButton { padding:5px 10px; border-radius:6px; color:#d7d7d7; }
QToolBar#main QToolButton:hover { background:#34363c; }
QToolBar#main QToolButton:pressed { background:#3d404a; }
QFrame#actionbar { background:#25262a; border-top:1px solid #34363c; }
QFrame#actionbar QToolButton { padding:5px 10px; border-radius:6px; color:#d7d7d7; }
QFrame#actionbar QToolButton:hover { background:#34363c; }
QFrame#actionbar QToolButton:pressed { background:#3d404a; }
QFrame#actionbar QToolButton:disabled { color:#6a6a6a; }
QToolButton#primary { background:#343a63; }
QToolButton#primary:hover { background:#454c80; }
QToolButton#primary:disabled { background:#2b2d33; }
QTreeWidget { border:1px solid #34363c; border-radius:6px; }
QTreeWidget::item { padding:2px 0; }
QTreeWidget::item:selected { background:#3a4a7a; }
QHeaderView::section { background:#2a2c31; color:#b9b9b9; border:0;
                       border-right:1px solid #34363c; padding:4px 6px; }
QLineEdit { background:#232427; border:1px solid #3a3c42; border-radius:6px;
            padding:5px 8px; }
QLineEdit:focus { border:1px solid #7c8cf8; }
QSplitter::handle { background:#34363c; }
QSplitter::handle:horizontal { width:3px; }
QSplitter::handle:vertical { height:3px; }
QStatusBar { background:#25262a; color:#b0b0b0; border-top:1px solid #34363c; }
QProgressBar { background:#232427; border:1px solid #3a3c42; border-radius:6px;
               text-align:center; color:#d0d0d0; }
QProgressBar::chunk { background:#4F46E5; border-radius:5px; }
QCheckBox { spacing:6px; }
"""


def _apply_dark(app):
    """Fusion dark palette so the viewer matches the report's dark identity."""
    app.setStyle('Fusion')
    p = QPalette()
    bg, base, text = QColor('#1e1f22'), QColor('#232427'), QColor('#d4d4d4')
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, bg)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Button, base)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.Highlight, QColor('#3a5a7a'))
    p.setColor(QPalette.HighlightedText, QColor('#ffffff'))
    app.setPalette(p)
    app.setStyleSheet(_QSS)


def _taskbar_identity():
    """Windows groups taskbar buttons by AppUserModelID; without our own the
    frozen exe inherits the host python's and shows its icon instead."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'LongVoThien.CodeGenCompareTool')
    except Exception:
        pass  # not Windows, or the call is unavailable: cosmetic either way


def run_viewer(old=None, new=None, exclude=(), arxml_only=False):
    app = QApplication.instance()
    owns = app is None
    if owns:
        _taskbar_identity()
        app = QApplication(sys.argv[:1])
    _apply_dark(app)
    app.setApplicationName('CodeGen Compare')
    app.setWindowIcon(app_icon())
    win = MainWindow(old, new, exclude, arxml_only)
    win.show()
    return app.exec() if owns else 0


if __name__ == '__main__':
    sys.exit(run_viewer())
