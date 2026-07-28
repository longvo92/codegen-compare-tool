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


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestFindInFile(unittest.TestCase):
    """Ctrl+F searches the rows of the file on screen."""

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

    def test_a_hit_on_either_side_counts_once(self):
        self._open('src/rename_conflict.c')
        hits = self.pane.find_matches('rtb_')
        self.assertTrue(hits)
        for row in hits:
            r = self.pane.rows[row]
            self.assertIn('rtb_', (r.old_txt or '') + (r.new_txt or ''))
        # one row, not one per side, or "3 of 8" would count lines twice
        self.assertEqual(len(hits), len(set(hits)))

    def test_search_is_case_insensitive_and_empty_finds_nothing(self):
        self._open('src/rename_conflict.c')
        self.assertEqual(self.pane.find_matches('RTB_'),
                         self.pane.find_matches('rtb_'))
        self.assertEqual(self.pane.find_matches('   '), [])

    def test_a_whole_added_file_is_searchable(self):
        # it renders through the one-sided path, which used to leave .rows
        # empty -- a file with no rows is a file the find box cannot see
        self._open('src/added.c')
        self.assertTrue(self.pane.rows)
        self.assertTrue(self.pane.find_matches('void'))

    def test_stepping_wraps_and_reports_position(self):
        self._open('src/rename_conflict.c')
        self.pane.open_find()
        self.pane._find_edit.setText('rtb_')
        for _ in range(5):
            self.app.processEvents()
        n = len(self.pane._hits)
        self.assertGreater(n, 1)
        self.assertEqual(self.pane._find_count.text(), '1 of {}'.format(n))
        for _ in range(n):  # once round the whole file
            self.pane.find_next()
        self.assertEqual(self.pane._find_count.text(), '1 of {}'.format(n))
        self.pane.find_prev()
        self.assertEqual(self.pane._find_count.text(), '{} of {}'.format(n, n))

    def test_the_query_survives_a_file_change_without_moving_the_pane(self):
        self._open('src/rename_conflict.c')
        self.pane.open_find()
        self.pane._find_edit.setText('rtb_')
        for _ in range(5):
            self.app.processEvents()
        self._open('src/real_change.c')
        self.assertEqual(self.pane._find_edit.text(), 'rtb_')
        # opening a file parks on its FIRST CHANGE; a query carried over from
        # another file must not quietly scroll somewhere else
        self.assertEqual(self.pane._hit_idx, -1)
        self.assertIn(self.pane.old_edit.textCursor().blockNumber(),
                      self.pane._stops)


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestChangeNavigationStopsAtTheEnd(unittest.TestCase):
    """next/prev report False at the ends instead of wrapping silently.

    The window uses that False to step into the next file, which is what makes
    F8 walk the whole compare; wrapping inside one file dead-ended the pass.
    """

    def setUp(self):
        from compare_tool.qtviewer.diffpane import DiffPane
        self.app = _app()
        self.results = scan(FIX / 'old', FIX / 'new')
        self.pane = DiffPane()
        self.pane.resize(1200, 600)
        self.pane.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.pane.show()
        self.addCleanup(self.pane.close)
        self.pane.show_file('src/rename_conflict.c',
                            self.results['src/rename_conflict.c'],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()

    def test_next_walks_the_file_then_stops(self):
        n = len(self.pane._stops)
        self.assertGreater(n, 1)
        self.pane.first_change()
        for i in range(n - 1):
            self.assertTrue(self.pane.next_change(), 'stopped at change {}'.format(i))
        self.assertFalse(self.pane.next_change())

    def test_prev_stops_at_the_first_change(self):
        self.pane.first_change()
        self.assertFalse(self.pane.prev_change())

    def test_a_file_with_no_change_stops_never_claims_to_move(self):
        self.pane.show_file('src/rename_only.c', self.results['src/rename_only.c'],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()
        self.assertFalse(self.pane.next_change())
        self.assertFalse(self.pane.prev_change())


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestWindowLevelReviewFlow(unittest.TestCase):
    """What the reviewer meets right after a scan, and how F7/F8 walk it."""

    def setUp(self):
        from compare_tool.qtviewer.app import MainWindow
        self.app = _app()
        self.win = MainWindow(str(FIX / 'old'), str(FIX / 'new'))
        self.win.resize(1400, 800)
        self.win.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.win.show()
        self.addCleanup(self.win.close)
        _settle(self.app, self.win)

    def _settle_ui(self):
        for _ in range(5):
            self.app.processEvents()

    def test_a_finished_scan_opens_on_the_first_change(self):
        rel = self.win._selected_rel()
        self.assertIsNotNone(rel, 'the scan left the diff pane empty')
        self.assertIn(self.win.results[rel]['status'], self.win._NAV_STATUS)
        # the first one in tree order, not just any
        self.assertEqual(rel, next(r for r in self.win._tree_rels()
                                   if self.win._is_nav(r)))

    def test_flipping_a_compare_rule_does_not_move_the_reviewer(self):
        self.win._reselect('src/rename_conflict.c')
        self._settle_ui()
        self.win.cb_comment.setChecked(False)
        self._settle_ui()
        self.assertEqual(self.win._selected_rel(), 'src/rename_conflict.c')

    def test_next_change_crosses_into_the_following_file(self):
        nav = [r for r in self.win._tree_rels() if self.win._is_nav(r)]
        self.assertGreater(len(nav), 1)
        self.win._reselect(nav[0])
        self._settle_ui()
        seen = [self.win._selected_rel()]
        for _ in range(60):  # bounded: pressing F8 must terminate, not loop
            self.win._next_change()
            self._settle_ui()
            rel = self.win._selected_rel()
            if rel != seen[-1]:
                seen.append(rel)
            if len(seen) > len(nav):
                break
        # every file with something to review, in tree order, then round again
        self.assertEqual(seen, nav + [nav[0]])

    def test_the_walk_wraps_back_to_the_first_file(self):
        nav = [r for r in self.win._tree_rels() if self.win._is_nav(r)]
        self.win._reselect(nav[-1])
        self._settle_ui()
        for _ in range(20):
            self.win._next_change()
            self._settle_ui()
            if self.win._selected_rel() == nav[0]:
                return
        self.fail('F8 never came back round to {}'.format(nav[0]))

    def test_prev_change_steps_back_a_file_at_its_last_change(self):
        nav = [r for r in self.win._tree_rels() if self.win._is_nav(r)]
        target = 'src/rename_conflict.c'  # the fixture file with two changes
        self.assertIn(target, nav)
        # the file after it, wrapping: rename_conflict.c is the last nav file
        # in this fixture, so this also covers stepping back over the wrap
        after = nav[(nav.index(target) + 1) % len(nav)]
        self.win._reselect(after)
        self._settle_ui()
        self.win._prev_change()
        self._settle_ui()
        self.assertEqual(self.win._selected_rel(), target)
        self.assertEqual(self.win.diff._cur_idx, len(self.win.diff._stops) - 1)

    def test_hide_identical_drops_only_identical_rows(self):
        before = self.win._tree_rels()
        identical = [r for r in before
                     if self.win.results[r]['status'] == 'identical']
        self.assertTrue(identical, 'fixture has no identical file to hide')
        self.win.cb_hide_identical.setChecked(True)
        self._settle_ui()
        after = self.win._tree_rels()
        self.assertEqual(after, [r for r in before if r not in identical])
        self.win.cb_hide_identical.setChecked(False)
        self._settle_ui()
        self.assertEqual(self.win._tree_rels(), before)

    def test_hide_identical_keeps_the_file_on_screen(self):
        self.win._reselect('src/real_change.c')
        self._settle_ui()
        self.win.cb_hide_identical.setChecked(True)
        self._settle_ui()
        self.assertEqual(self.win._selected_rel(), 'src/real_change.c')

    def test_hiding_rows_never_changes_a_verdict_or_the_counts(self):
        # the filter is display-only: the record the export is built from must
        # not notice it at all
        before = {rel: r['status'] for rel, r in self.win.results.items()}
        raw = dict(self.win._raw_results)
        self.win.cb_hide_identical.setChecked(True)
        self._settle_ui()
        self.assertEqual({rel: r['status'] for rel, r in self.win.results.items()},
                         before)
        self.assertEqual(set(self.win._raw_results), set(raw))


if __name__ == '__main__':
    unittest.main()
