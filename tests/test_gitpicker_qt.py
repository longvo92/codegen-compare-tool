"""Exercise Git compare through Qt with real commits and snapshots."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from test_gitsource import _git, _git_available, _graph_fixture

from compare_tool import gitsource

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

    from compare_tool.qtviewer.app import MainWindow
    from compare_tool.qtviewer.gitpicker import CommitPicker, GitComparison
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT and _git_available(), 'Git and PySide6 required')
class TestGitPicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name) / 'repo'
        cls.root.mkdir()
        cls.graph = _graph_fixture(cls.root)
        cls.folder = str(cls.root / 'gen')
        outside = cls.root / 'docs'
        outside.mkdir()
        (outside / 'README.md').write_text('Outside the selected folder\n', encoding='utf-8')
        _git(cls.root, 'add', 'docs')
        _git(cls.root, 'commit', '-qm', 'Only change docs')
        _git(cls.root, 'tag', 'docs-only')
        cls.actual_head = gitsource.resolve_sha(cls.root, 'HEAD')
        _git(cls.root, 'checkout', '-q', 'unmerged')
        _git(cls.root, 'commit', '--allow-empty', '-qm', 'No folder changes on unmerged tip')
        _git(cls.root, 'tag', 'unmerged-tip')
        _git(cls.root, 'checkout', '-q', 'main')
        (cls.root / 'untracked').mkdir()

    def wait(self, ready):
        deadline = time.monotonic() + 15
        while not ready():
            self.app.processEvents()
            if time.monotonic() >= deadline:
                self.fail('Git comparison did not settle')
            time.sleep(0.01)

    def dialog(self, parent=None):
        dlg = CommitPicker(parent, self.folder)
        dlg.setAttribute(Qt.WA_DontShowOnScreen)
        dlg.show()
        self.addCleanup(dlg.close)
        self.wait(lambda: dlg.worker is None)
        return dlg

    def click(self, dlg, commit, modifier=None):
        if modifier is None:
            modifier = Qt.NoModifier
        row = next(i for i, c in enumerate(dlg.model.commits) if c.sha == commit.sha)
        index = dlg.model.index(row, 1)
        dlg.table.scrollTo(index)
        pos = dlg.table.visualRect(index).center()
        QTest.mouseClick(dlg.table.viewport(), Qt.LeftButton, modifier, pos)
        return pos

    def choose_action(self, dlg, pos, label):
        case = self

        class ChoosingMenu(QMenu):
            def exec(self, _pos):
                action = next(a for a in self.actions() if a.text() == label)
                case.assertTrue(action.isEnabled())
                return action

        with patch('compare_tool.qtviewer.gitpicker.QMenu', ChoosingMenu):
            viewport = dlg.table.viewport()
            QTest.mousePress(viewport, Qt.RightButton, pos=pos)
            QTest.mouseRelease(viewport, Qt.RightButton, pos=pos)
            QApplication.sendEvent(
                viewport, QContextMenuEvent(QContextMenuEvent.Mouse, pos, viewport.mapToGlobal(pos)))

    def test_pair_menu_and_direction_drive_scan_and_html(self):
        win = MainWindow(settings=Mock(value=lambda _key, default: default))
        win.setAttribute(Qt.WA_DontShowOnScreen)
        self.addCleanup(win.close)
        dlg = self.dialog(win)
        self.click(dlg, self.graph['head'])
        pos = self.click(dlg, self.graph['base'], Qt.ControlModifier)
        self.wait(lambda: dlg.worker is None)
        self.assertIn('Ordered by ancestry', dlg.preview.text())
        self.choose_action(dlg, pos, 'Swap baseline/current')
        self.assertIn('Direction swapped', dlg.preview.text())
        self.choose_action(dlg, pos, 'Swap baseline/current')
        self.choose_action(dlg, pos, 'Compare selected')
        with patch('compare_tool.qtviewer.app.pick_commit', return_value=dlg.chosen):
            win._pick_commit()
        self.wait(lambda: win._git_worker is None and bool(win._raw_results))
        self.assertEqual(win._raw_results['model.c']['status'], 'real-change')
        self.assertEqual((Path(win.old) / 'model.c').read_text(), 'int limit = 1;\n')
        self.assertEqual((Path(win.new) / 'model.c').read_text(), 'int limit = 2;\n')
        self.assertIn('v1.0', win.diff._old_label[0])
        self.assertIn('v2.0', win.diff._new_label[0])
        with patch('compare_tool.qtviewer.app.pick_commit', return_value=None) as picker:
            self.wait(lambda: not win.worker.isRunning())
            win._pick_commit()
            picker.assert_called_once_with(win, self.folder)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.html'
            with patch('compare_tool.qtviewer.app.QFileDialog.getSaveFileName',
                       return_value=(str(path), '')) as save, patch(
                           'compare_tool.qtviewer.app.QMessageBox',
                           Mock(question=Mock(return_value=QMessageBox.No), Yes=QMessageBox.Yes)):
                win._export_report()
            self.assertEqual(Path(save.call_args.args[2]).parent, self.root)
            report = path.read_text(encoding='utf-8')
            self.assertIn('v1.0', report)
            self.assertIn('v2.0', report)

    def test_working_tree_action_includes_uncommitted_content(self):
        win = MainWindow(settings=Mock(value=lambda _key, default: default))
        win.setAttribute(Qt.WA_DontShowOnScreen)
        self.addCleanup(win.close)
        dlg = self.dialog(win)
        pos = self.click(dlg, self.graph['head'])
        self.choose_action(dlg, pos, 'Compare with working tree')
        self.assertIsNone(dlg.chosen.current)
        source = Path(self.folder) / 'model.c'
        previous = source.read_bytes()
        try:
            source.write_text('int limit = 9;\n', encoding='utf-8')
            win._prepare_git_comparison(dlg.chosen)
            self.wait(lambda: win._git_worker is None and bool(win._raw_results))
            self.assertEqual(win.new, self.folder)
            self.assertEqual(win._raw_results['model.c']['status'], 'real-change')
            self.assertIn('Includes uncommitted changes', win.diff._new_label[1])
        finally:
            source.write_bytes(previous)

    def test_search_and_revision_keep_graph_and_expand_only_on_request(self):
        dlg = self.dialog()
        with patch('compare_tool.qtviewer.gitpicker.QFileDialog.getExistingDirectory',
                   return_value='') as browse:
            dlg.find.setFocus()
            dlg.find.setText('v1.0')
            QTest.keyClick(dlg.find, Qt.Key_Return)
            self.assertEqual(dlg.model.commits[dlg.table.currentIndex().row()].sha,
                             self.graph['base'].sha)
            self.assertEqual(len(dlg.tips), 1)
            dlg.rev.setFocus()
            dlg.rev.setText('unmerged-tip')
            QTest.keyClick(dlg.rev, Qt.Key_Return)
            self.wait(lambda: dlg.worker is None)
        browse.assert_not_called()
        self.assertIn('additional revisions', dlg.where.text())
        self.assertEqual({c.sha for c in dlg._selected()},
                         {self.graph['head'].sha, self.graph['unmerged'].sha})
        self.assertIn(self.graph['unmerged'].sha[:12], dlg.notice.text())
        self.assertNotIn('No folder changes on unmerged tip',
                         {c.subject for c in dlg.model.commits})

    def test_folder_change_discards_history_already_in_flight(self):
        entered, release = Event(), Event()
        actual_history = gitsource.folder_history

        def wait_for_folder(*args, **kwargs):
            if not entered.is_set():
                entered.set()
                release.wait(10)
            return actual_history(*args, **kwargs)

        with patch.object(gitsource, 'folder_history', side_effect=wait_for_folder):
            dlg = CommitPicker(None, self.folder)
            self.addCleanup(dlg.close)
            try:
                self.wait(entered.is_set)
                dlg.folder = str(self.root)
                dlg._reload()
            finally:
                release.set()
            self.wait(lambda: dlg.worker is None)
        self.assertEqual(dlg.sub, '')
        self.assertIn('whole repository', dlg.where.text())
        self.assertEqual([c.sha for c in dlg._selected()], [self.actual_head])

    def test_default_and_go_to_revision_use_folder_history(self):
        dlg = self.dialog()
        latest = self.graph['head'].sha
        self.assertEqual([c.sha for c in dlg._selected()], [latest])
        self.assertNotIn(self.actual_head, {c.sha for c in dlg.model.commits})
        dlg.find.setText('Only change docs')
        dlg._find_next()
        self.assertIn('No matching commit', dlg.notice.text())

        dlg.rev.setText('docs-only')
        dlg._go_to_revision()
        self.wait(lambda: dlg.worker is None)
        self.assertEqual(dlg.tips, (self.actual_head,))
        self.assertEqual([c.sha for c in dlg._selected()], [latest])
        self.assertIn(latest[:12], dlg.notice.text())

        dlg.rev.setText('v1.0')
        dlg._go_to_revision()
        self.wait(lambda: dlg.worker is None)
        self.assertEqual({c.sha for c in dlg._selected()}, {latest, self.graph['base'].sha})
        self.assertIn('Ordered by ancestry', dlg.preview.text())

    def test_folder_switch_and_empty_history(self):
        dlg = self.dialog()
        dlg.folder = str(self.root / 'docs')
        dlg._reload()
        self.wait(lambda: dlg.worker is None)
        self.assertEqual([c.sha for c in dlg._selected()], [self.actual_head])
        self.assertEqual(dlg.model.rowCount(), 1)

        dlg.rev.setText('v1.0')
        dlg._go_to_revision()
        self.wait(lambda: dlg.worker is None)
        self.assertEqual([c.sha for c in dlg._selected()], [self.actual_head])
        self.assertIn('No folder changes found', dlg.notice.text())

        dlg.folder = str(self.root / 'untracked')
        dlg._reload()
        self.wait(lambda: dlg.worker is None)
        self.assertEqual(dlg.model.rowCount(), 0)
        self.assertFalse(dlg._selected())
        self.assertIn('No commits changed this folder', dlg.notice.text())

    def test_unborn_head_displays_empty_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root, 'init', '-q')
            (root / 'gen').mkdir()
            dlg = CommitPicker(None, str(root / 'gen'))
            try:
                self.wait(lambda: dlg.worker is None)
                self.assertEqual(dlg.model.rowCount(), 0)
                self.assertIn('HEAD has no commits', dlg.notice.text())
            finally:
                dlg.close()

    def test_next_page_keeps_existing_rows_and_lanes(self):
        with patch('compare_tool.qtviewer.gitpicker._PAGE', 2):
            dlg = self.dialog()
            before = list(dlg.model.rows)
            self.assertEqual(len(before), 2)
            dlg._scrolled(dlg.table.verticalScrollBar().maximum())
            self.wait(lambda: dlg.worker is None)
            self.assertEqual(dlg.model.rows[:2], before)
            self.assertEqual(len({c.sha for c in dlg.model.commits}), 4)
            dlg.find.setText('Initial generation')
            dlg._find_next()
            self.wait(lambda: dlg.worker is None)
            self.assertEqual(dlg.model.commits[dlg.table.currentIndex().row()].sha,
                             self.graph['base'].sha)
            self.assertEqual(len({c.sha for c in dlg.model.commits}), 5)
            self.assertFalse(dlg.more)
            self.assertFalse(dlg.model.lanes.pending)

    def test_second_export_failure_keeps_previous_sources(self):
        win = MainWindow(settings=Mock(value=lambda _key, default: default))
        self.addCleanup(win.close)
        previous = (self.folder, self.folder)
        win.old, win.new = previous
        missing = self.graph['head']._replace(sha='1' * 40)
        choice = GitComparison(self.folder, self.root, 'gen', self.graph['base'], missing)
        with patch('compare_tool.qtviewer.app.QMessageBox') as messages:
            win._prepare_git_comparison(choice)
            self.wait(lambda: win._git_worker is None)
        messages.critical.assert_called_once()
        self.assertEqual((win.old, win.new), previous)
        self.assertIsNone(win.worker)
