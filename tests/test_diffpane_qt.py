"""Diff pane behaviour that only shows up once Qt is really rendering.

Skipped when PySide6 is absent, so the rest of the suite still runs headless
(see the "viewer logic that can be Qt-free must be Qt-free" rule).
"""
import os
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:                                  # pragma: no cover
    HAVE_QT = False

from compare_tool.scanner import scan

FIX = Path(__file__).parent / 'fixtures'
_APP = None


def _app():
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _settle(app, win, timeout=30.0):
    """Spin the event loop until the scan thread has delivered its results.

    MainWindow scans in a ScanWorker, so a fixed number of processEvents turns
    is a race: it passes on a warm checkout and fails on a cold one, which is
    the worst kind of test.
    """
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        worker = getattr(win, 'worker', None)
        if win._raw_results and not (worker and worker.isRunning()):
            for _ in range(5):
                app.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError('scan did not finish within {}s'.format(timeout))


def _backgrounds(editor):
    """Per block: the background colours actually attached to it."""
    doc = editor.document()
    out = []
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        marks = []
        if block.blockFormat().background().style() != Qt.NoBrush:
            marks.append('block')
        for run in block.textFormats():
            if run.format.background().style() != Qt.NoBrush:
                marks.append('char{}:{}'.format(run.start, run.start + run.length))
        out.append(marks)
    return out


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestCaretDoesNotPaint(unittest.TestCase):
    """Clicking inside a coloured span must not colour the next file.

    setPlainText stamps the caret's char format across the whole new document,
    so a caret left sitting in a changed span turns every file opened
    afterwards into a wall of colour on that pane -- and an all-green pane
    reads as "everything changed", which is the one thing the tool must never
    say by accident.
    """

    REL = 'a2l/comment_only.a2l'
    OTHER = 'a2l/cal.a2l'

    def setUp(self):
        from compare_tool.qtviewer.diffpane import DiffPane
        self.app = _app()
        self.results = scan(FIX / 'old', FIX / 'new')
        self.pane = DiffPane()
        self.pane.resize(1200, 600)
        self.pane.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.pane.show()
        self.addCleanup(self.pane.close)

    def _open(self, rel):
        self.pane.show_file(rel, self.results[rel],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()

    def _click_in_span(self, editor, pos):
        cur = editor.textCursor()
        cur.setPosition(pos)
        editor.setTextCursor(cur)
        self.app.processEvents()

    def test_caret_in_a_changed_span_does_not_colour_the_next_file(self):
        self._open(self.REL)
        clean = _backgrounds(self.pane.new_edit)
        # the caret lands inside the highlighted date on line 1
        self._click_in_span(self.pane.new_edit, 14)
        self.assertNotEqual(
            self.pane.new_edit.currentCharFormat().background().style(),
            Qt.NoBrush, 'fixture no longer highlights that position')

        self._open(self.OTHER)
        other = _backgrounds(self.pane.new_edit)
        plain = [i for i, m in enumerate(other) if not m]
        self.assertTrue(plain, 'every row of cal.a2l came back coloured')

        self._open(self.REL)
        self.assertEqual(_backgrounds(self.pane.new_edit), clean)

    def test_the_same_holds_for_the_baseline_pane(self):
        self._open(self.REL)
        clean = _backgrounds(self.pane.old_edit)
        self._click_in_span(self.pane.old_edit, 14)
        self._open(self.OTHER)
        self._open(self.REL)
        self.assertEqual(_backgrounds(self.pane.old_edit), clean)


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestMinimapOnOneSidedFiles(unittest.TestCase):
    """A whole added or deleted file still gets a map to scroll by."""

    def setUp(self):
        from compare_tool.qtviewer.diffpane import DiffPane
        self.app = _app()
        self.results = scan(FIX / 'old', FIX / 'new')
        self.pane = DiffPane()
        self.pane.resize(1200, 500)
        self.pane.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.pane.show()
        self.addCleanup(self.pane.close)

    def _open(self, rel):
        self.pane.show_file(rel, self.results[rel],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()

    def test_added_and_deleted_files_have_a_map(self):
        for rel, side in (('src/added.c', 'new'), ('src/deleted.h', 'old')):
            self._open(rel)
            self.assertTrue(self.pane.minimap._rows, rel)
            # driven by the pane that holds the text, or the slider sits at the
            # top of an empty document for ever
            edit = self.pane.new_edit if side == 'new' else self.pane.old_edit
            self.assertIs(self.pane.minimap._editor, edit, rel)

    def test_a_one_sided_map_carries_no_diff_colour(self):
        # the pane is already one solid colour; repeating it on the map would
        # be a rectangle carrying no information
        self._open('src/added.c')
        self.assertEqual({r.mode for r in self.pane.minimap._rows}, {'ctx'})

    def test_two_pane_files_go_back_to_the_baseline_editor(self):
        self._open('src/added.c')
        self._open('src/real_change.c')
        self.assertIs(self.pane.minimap._editor, self.pane.old_edit)
        self.assertTrue(self.pane.minimap._rows)


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestQuickChangesJump(unittest.TestCase):
    """Activating a quick-changes row must land on that object's line.

    The panel carries the name as spelled in the file for exactly this; before
    it did, every row opened its file at change 1, so a row about the eighth
    CHARACTERISTIC looked like it pointed at the wrong one.
    """

    def _window(self, old, new):
        from compare_tool.qtviewer.app import MainWindow
        self.app = _app()
        win = MainWindow(str(old), str(new))
        win.resize(1400, 800)
        win.setAttribute(Qt.WA_DontShowOnScreen, True)
        win.show()
        self.addCleanup(win.close)
        _settle(self.app, win)
        return win

    def _rows(self, win):
        from compare_tool.qtviewer.summary import KEY_ROLE
        panel = win.summary
        out = []
        for i in range(panel.topLevelItemCount()):
            head = panel.topLevelItem(i)
            for j in range(head.childCount()):
                child = head.child(j)
                out.append((child, child.data(0, KEY_ROLE)))
        return panel, out

    def _check(self, old, new):
        win = self._window(old, new)
        panel, rows = self._rows(win)
        self.assertTrue(rows, 'fixture produced no quick-changes rows')
        for item, key in rows:
            self.assertTrue(key, 'row {!r} carries no name'.format(item.text(0)))
            panel.itemClicked.emit(item, 0)
            for _ in range(5):
                self.app.processEvents()
            landed = win.diff.old_edit.textCursor().blockNumber()
            self.assertLess(landed, len(win.diff.rows))
            row = win.diff.rows[landed]
            self.assertIn(key, (row.new_txt or '') + (row.old_txt or ''),
                          'row {!r} landed on line {}'.format(item.text(0), landed))

    def test_every_row_lands_on_its_own_object(self):
        self._check(FIX / 'old', FIX / 'new')

    def test_every_row_lands_on_its_own_object_in_the_model_fixture(self):
        self._check(FIX / 'model_old', FIX / 'model_new')


if __name__ == '__main__':
    unittest.main()
