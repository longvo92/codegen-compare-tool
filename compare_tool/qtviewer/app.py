"""Viewer main window: folder tree on the left, diff pane on the right.

The scan runs on a :class:`ScanWorker` thread; the window only reacts to its
signals. Fail-safe stays first-class: a worker crash or any uncompared path
raises a loud red banner -- an incomplete compare must never look clean.
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QProgressBar,
                               QSplitter, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..diff_engine import RULES
from ..scanner import summarize
from .diffpane import DiffPane
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
        self.results = {}
        self.worker = None

        self.setWindowTitle('AUTOSAR CodeGen Compare — viewer')
        self.resize(1200, 800)

        self.banner = QLabel()
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet('background:#4a1d1d; color:#ffd6d6; padding:6px 10px;'
                                  'font-weight:bold; border-bottom:1px solid #b04a4a;')

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['File', 'Status'])
        self.tree.setColumnWidth(0, 380)
        self.tree.setUniformRowHeights(True)
        self.tree.itemSelectionChanged.connect(self._on_select)

        # filter row: path search + status toggles. The full tree is shown by
        # default (like Beyond Compare's folder view) -- untick a box to hide
        # Identical / Unimportant files when you want to focus on real changes.
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('Filter by path…')
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._refresh_tree)
        self.cb_identical = QCheckBox('Identical')
        self.cb_identical.setChecked(True)
        self.cb_unimportant = QCheckBox('Unimportant')
        self.cb_unimportant.setChecked(True)
        self.cb_identical.toggled.connect(self._refresh_tree)
        self.cb_unimportant.toggled.connect(self._refresh_tree)
        toggles = QHBoxLayout()
        toggles.setContentsMargins(0, 0, 0, 0)
        toggles.addWidget(QLabel('Show:'))
        toggles.addWidget(self.cb_identical)
        toggles.addWidget(self.cb_unimportant)
        toggles.addStretch(1)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(6, 6, 6, 0)
        lv.setSpacing(4)
        lv.addWidget(self.filter_edit)
        lv.addLayout(toggles)
        lv.addWidget(self.tree, 1)

        self.diff = DiffPane()

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(self.diff)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([400, 800])

        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.banner)
        v.addWidget(split)
        self.setCentralWidget(central)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(240)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)

        tb = self.addToolBar('main')
        tb.setMovable(False)
        act_open = QAction('Open folders…', self)
        act_open.triggered.connect(self._pick_folders)
        act_rescan = QAction('Rescan', self)
        act_rescan.triggered.connect(self._start_scan)
        tb.addAction(act_open)
        tb.addAction(act_rescan)
        tb.addSeparator()
        act_prev = QAction('◀ Prev change', self)
        act_prev.setShortcut('F7')
        act_prev.triggered.connect(lambda: self.diff.prev_change())
        act_next = QAction('Next change ▶', self)
        act_next.setShortcut('F8')
        act_next.triggered.connect(lambda: self.diff.next_change())
        tb.addAction(act_prev)
        tb.addAction(act_next)

        if self.old and self.new:
            self._start_scan()
        else:
            self._pick_folders()

    # --- folder selection ---

    def _pick_folders(self):
        o = QFileDialog.getExistingDirectory(self, 'Select OLD folder', self.old or '')
        if not o:
            return
        n = QFileDialog.getExistingDirectory(self, 'Select NEW folder', self.new or o)
        if not n:
            return
        self.old, self.new = o, n
        self._start_scan()

    # --- scan lifecycle ---

    def _start_scan(self):
        if not (self.old and self.new):
            return
        if self.worker and self.worker.isRunning():
            return
        self.banner.setVisible(False)
        self.tree.clear()
        self.diff.clear()
        self.results = {}
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # busy/indeterminate until first tick
        self.setWindowTitle('AUTOSAR CodeGen Compare — {}  →  {}'.format(self.old, self.new))
        self.statusBar().showMessage('Scanning…')
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
        self.results = results
        self._refresh_tree()
        counts = summarize(results)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.progress.setVisible(False)
        if counts['error']:
            errs = sorted(rel for rel, r in results.items() if r['status'] == 'error')
            shown = ', '.join(errs[:20]) + (' …' if len(errs) > 20 else '')
            self.banner.setText('⚠ COMPARE INCOMPLETE — {} path(s) NOT compared '
                                '(treat as potentially changed): {}'.format(len(errs), shown))
            self.banner.setVisible(True)
        self.statusBar().showMessage(
            '{real-change} modified · {ignorable-only} unimportant · {added} added · '
            '{deleted} deleted · {identical} identical · {error} error(s)'.format(**counts))

    def _on_fail(self, msg):
        self.progress.setVisible(False)
        self.banner.setText('‼ SCAN FAILED — no results (treat everything as '
                            'potentially changed): {}'.format(msg))
        self.banner.setVisible(True)
        self.statusBar().showMessage('SCAN FAILED')

    # --- tree fill + selection ---

    def _refresh_tree(self):
        """Rebuild the tree from results under the current filter + toggles.
        Cheap enough to run on every keystroke; selection is not preserved."""
        self.tree.clear()
        if not self.results:
            return
        nodes = filter_nodes(build_nodes(self.results),
                             show_identical=self.cb_identical.isChecked(),
                             show_unimportant=self.cb_unimportant.isChecked(),
                             text=self.filter_edit.text())
        self._fill_tree(nodes)

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

    def _on_select(self):
        items = self.tree.selectedItems()
        if not items:
            return
        rel = items[0].data(0, REL_ROLE)
        if rel and rel in self.results:
            self.diff.show_file(rel, self.results[rel], self.old, self.new)


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


def run_viewer(old=None, new=None, exclude=(), arxml_only=False):
    app = QApplication.instance()
    owns = app is None
    if owns:
        app = QApplication(sys.argv[:1])
    _apply_dark(app)
    win = MainWindow(old, new, exclude, arxml_only)
    win.show()
    return app.exec() if owns else 0


if __name__ == '__main__':
    sys.exit(run_viewer())
