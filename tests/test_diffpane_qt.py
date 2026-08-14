"""Diff pane behaviour that only shows up once Qt is really rendering.

Skipped when PySide6 is absent, so the rest of the suite still runs headless
(see the "viewer logic that can be Qt-free must be Qt-free" rule).
"""
import os
import tempfile
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
class TestCurrentFunctionCaption(unittest.TestCase):
    """The "current function" caption -- where in the file the reviewer is."""

    def setUp(self):
        from compare_tool.qtviewer.diffpane import DiffPane
        self.app = _app()
        self.results = scan(FIX / 'old', FIX / 'new')
        self.pane = DiffPane()
        self.pane.resize(1000, 600)
        self.pane.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.pane.show()
        self.addCleanup(self.pane.close)

    def _open(self, rel):
        self.pane.show_file(rel, self.results[rel],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()

    def test_opens_on_the_changed_functions_scope(self):
        # the real change in real_change.c is inside Calc_step, so the file
        # opens with that named in the caption -- not the banner line above it
        self._open('src/real_change.c')
        self.assertIn('Calc_step', self.pane._fn.text())
        self.assertTrue(self.pane._fn.isVisible())

    def test_row_labels_align_with_rows(self):
        self._open('src/real_change.c')
        self.assertEqual(len(self.pane._row_fn), len(self.pane.rows))
        self.assertIn('Calc_step', self.pane._row_fn)

    def test_one_sided_file_is_captioned_too(self):
        # a whole added file still has a scope: New_step
        self._open('src/added.c')
        self.assertIn('New_step', self.pane._row_fn)

    def test_caption_clears_between_files(self):
        # deleted.h holds only a declaration -- no function body -- so its
        # caption must not keep the previous file's function name
        self._open('src/real_change.c')
        self._open('src/deleted.h')
        self.assertNotIn('Calc_step', self.pane._fn.text())


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
class TestStickyHeaderAndScrollbar(unittest.TestCase):
    """The pinned "current function" header and the single vertical scrollbar."""

    def setUp(self):
        from compare_tool.qtviewer.diffpane import DiffPane
        self.app = _app()
        self.results = scan(FIX / 'old', FIX / 'new')
        self.pane = DiffPane()
        self.pane.resize(1000, 400)
        self.pane.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.pane.show()
        self.addCleanup(self.pane.close)

    def _open(self, rel):
        self.pane.show_file(rel, self.results[rel],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(6):
            self.app.processEvents()

    def _long_c(self):
        """A tall two-pane file: real_change.c is a handful of lines, so its
        function signature never scrolls off and the sticky would never show.
        Build one long enough that it does."""
        tmp = Path(tempfile.mkdtemp())
        (tmp / 'old').mkdir()
        (tmp / 'new').mkdir()
        body = '\n'.join('  a[{}] = {};'.format(i, i) for i in range(80))
        old = 'void LongFn(void)\n{\n' + body + '\n  a[0] = 1;\n}\n'
        new = 'void LongFn(void)\n{\n' + body + '\n  a[0] = 2;\n}\n'
        (tmp / 'old' / 'm.c').write_text(old)
        (tmp / 'new' / 'm.c').write_text(new)
        return tmp

    def test_only_the_driving_pane_shows_a_vertical_scrollbar(self):
        self._open('src/real_change.c')  # two-pane: old drives
        self.assertEqual(self.pane.old_edit.verticalScrollBarPolicy(),
                         Qt.ScrollBarAsNeeded)
        self.assertEqual(self.pane.new_edit.verticalScrollBarPolicy(),
                         Qt.ScrollBarAlwaysOff)

    def test_added_file_shows_no_scrollbar_over_the_minimap(self):
        # a whole added file's text is on the NEW (right) pane, which drives --
        # but the minimap sits immediately to its right, so a bar there would
        # collide with it. It stays off; the minimap, wheel and keyboard scroll.
        self._open('src/added.c')
        self.assertIs(self.pane._drive, self.pane.new_edit)
        self.assertEqual(self.pane.new_edit.verticalScrollBarPolicy(),
                         Qt.ScrollBarAlwaysOff)
        self.assertEqual(self.pane.old_edit.verticalScrollBarPolicy(),
                         Qt.ScrollBarAlwaysOff)

    def test_sticky_pins_the_function_once_it_scrolls_off(self):
        tmp = self._long_c()
        results = scan(tmp / 'old', tmp / 'new')
        self.pane.show_file('m.c', results['m.c'], str(tmp / 'old'), str(tmp / 'new'))
        for _ in range(6):
            self.app.processEvents()
        # at the top the signature line is on screen: nothing to pin
        self.pane._drive.verticalScrollBar().setValue(0)
        for _ in range(4):
            self.app.processEvents()
        self.assertFalse(self.pane._sticky_old.isVisible())
        # scrolled deep into the body: the signature is pinned at the top
        self.pane._drive.verticalScrollBar().setValue(50)
        for _ in range(4):
            self.app.processEvents()
        self.assertTrue(self.pane._sticky_old.isVisible())
        self.assertIn('LongFn', self.pane._sticky_old.text())

    def test_sticky_is_c_only(self):
        # an ARXML scope is a nested SHORT-NAME chain, not a one-line signature,
        # so no sticky even when a deep hunk scrolls its element off the top
        tmp = Path(tempfile.mkdtemp())
        (tmp / 'old').mkdir()
        (tmp / 'new').mkdir()
        rows = '\n'.join('    <ITEM UUID="{0}">v{0}</ITEM>'.format(i)
                         for i in range(80))
        head = ('<AUTOSAR><AR-PACKAGES><AR-PACKAGE>\n'
                '  <SHORT-NAME>Pkg</SHORT-NAME>\n  <ELEMENTS>\n')
        tail = '\n  </ELEMENTS>\n</AR-PACKAGE></AR-PACKAGES></AUTOSAR>\n'
        (tmp / 'old' / 'm.arxml').write_text(head + rows + '\n    <V>1</V>' + tail)
        (tmp / 'new' / 'm.arxml').write_text(head + rows + '\n    <V>2</V>' + tail)
        results = scan(tmp / 'old', tmp / 'new')
        self.pane.show_file('m.arxml', results['m.arxml'],
                            str(tmp / 'old'), str(tmp / 'new'))
        for _ in range(6):
            self.app.processEvents()
        self.pane._drive.verticalScrollBar().setValue(50)
        for _ in range(4):
            self.app.processEvents()
        self.assertFalse(self.pane._sticky_old.isVisible())
        self.assertFalse(self.pane._sticky_new.isVisible())

    def test_sticky_clears_on_message_pages(self):
        tmp = self._long_c()
        results = scan(tmp / 'old', tmp / 'new')
        self.pane.show_file('m.c', results['m.c'], str(tmp / 'old'), str(tmp / 'new'))
        for _ in range(6):
            self.app.processEvents()
        self.pane._drive.verticalScrollBar().setValue(50)
        for _ in range(4):
            self.app.processEvents()
        self.pane.clear()
        self.assertFalse(self.pane._sticky_old.isVisible())
        self.assertFalse(self.pane._sticky_new.isVisible())


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestZipAsSource(unittest.TestCase):
    """A .zip artifact dropped or picked as a side is unpacked, compared as a
    folder, and labelled by its file name -- not the temp path it landed in."""

    def _zip(self, root, name, files):
        import zipfile
        path = root / name
        with zipfile.ZipFile(path, 'w') as zf:
            for arc, text in files.items():
                zf.writestr(arc, text)
        return path

    def _window(self):
        from compare_tool.qtviewer.app import MainWindow
        self.app = _app()
        win = MainWindow(None, None)
        win.resize(1200, 700)
        win.setAttribute(Qt.WA_DontShowOnScreen, True)
        win.show()
        self.addCleanup(win.close)
        return win

    def test_zip_sides_are_unpacked_compared_and_labelled(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        oldz = self._zip(tmp, 'baseline.zip',
                         {'gen/m.c': 'void f(void)\n{\n  x = 1;\n}\n'})
        newz = self._zip(tmp, 'current.zip',
                         {'gen/m.c': 'void f(void)\n{\n  x = 2;\n}\n'})
        win = self._window()
        self.assertTrue(win._use_source('old', str(oldz)))
        self.assertTrue(win._use_source('new', str(newz)))
        # each side descended into the lone 'gen' wrapper and points at real files
        self.assertTrue(Path(win.old).is_dir())
        self.assertIn('m.c', [p.name for p in Path(win.old).iterdir()])
        # export label and pane banner both name the zip, not the temp folder
        self.assertEqual(win._old_label, 'baseline.zip')
        self.assertEqual(win._new_label, 'current.zip')
        self.assertEqual(win.diff._old_label[0], 'baseline.zip')
        self.assertEqual(win.diff._new_label[0], 'current.zip')
        win._start_scan()
        _settle(self.app, win)
        self.assertTrue(win._raw_results)  # the compare actually ran

    def test_a_folder_side_clears_a_prior_zip_label(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        z = self._zip(tmp, 'drop.zip', {'gen/m.c': 'int a;\n'})
        plain = tmp / 'plainfolder'
        plain.mkdir()
        (plain / 'm.c').write_text('int a;\n')
        win = self._window()
        win._use_source('old', str(z))
        self.assertEqual(win._old_label, 'drop.zip')
        # picking a plain folder for the same side must drop the zip label
        win._use_source('old', str(plain))
        self.assertIsNone(win._old_label)
        self.assertIsNone(win.diff._old_label)


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

    def _match_marks(self):
        return sum(len(s) for s in self.pane._sel_match)

    def _type(self, text):
        self.pane._find_edit.setText(text)
        for _ in range(5):
            self.app.processEvents()

    def test_a_query_that_stops_matching_takes_its_highlights_with_it(self):
        # typing on past the last hit ("begin" -> "beginal") said "No match"
        # while the old word stayed lit, which reads as the wrong answer
        self._open('a2l/comment_only.a2l')
        self.pane.open_find()
        self._type('begin')
        self.assertGreater(self._match_marks(), 0)
        self._type('beginal')
        self.assertEqual(self.pane._find_count.text(), 'No match')
        self.assertEqual(self._match_marks(), 0)

    def test_clearing_the_box_clears_the_marks(self):
        self._open('a2l/comment_only.a2l')
        self.pane.open_find()
        self._type('begin')
        self._type('')
        self.assertEqual(self._match_marks(), 0)
        self.assertEqual(self.pane._find_count.text(), '')

    def test_closing_the_bar_clears_the_marks(self):
        self._open('a2l/comment_only.a2l')
        self.pane.open_find()
        self._type('begin')
        self.pane.close_find()
        for _ in range(5):
            self.app.processEvents()
        self.assertEqual(self._match_marks(), 0)

    def test_every_occurrence_is_marked_not_only_the_current_one(self):
        self._open('a2l/comment_only.a2l')
        self.pane.open_find()
        self._type('begin')
        # one mark per occurrence per pane that has the row
        self.assertGreaterEqual(self._match_marks(), len(self.pane._hits))

    def test_the_current_change_marker_survives_a_cleared_search(self):
        # the current-change gutter arrow and the search highlights are
        # tracked separately; clearing the search used to wipe the block the
        # reviewer is standing on as well (back when both shared one
        # extraSelections list)
        self._open('src/rename_conflict.c')
        self.pane.open_find()
        self._type('rtb_')
        self._type('')
        self.assertTrue(self.pane.old_edit._cur_rows or self.pane.new_edit._cur_rows)

    def test_leaving_a_file_takes_its_marks_with_it(self):
        self._open('src/rename_conflict.c')
        self.pane.open_find()
        self._type('rtb_')
        self._open('src/real_change.c')  # no rtb_ in this one
        self.assertEqual(self._match_marks(), 0)

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
        # same.h is identical -- no hunks at all, real or noise -- so there is
        # truly nothing to step to regardless of what is muted
        self.pane.show_file('src/same.h', self.results['src/same.h'],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()
        self.assertFalse(self.pane.next_change())
        self.assertFalse(self.pane.prev_change())

    def test_a_noise_only_file_is_still_navigable_while_unmuted(self):
        # rename_only.c has no real change, only renames (mode 'minor'); shown
        # (the default, nothing muted) they are themselves valid F7/F8 stops,
        # but landing on one offers nothing to sign off -- noise never enters
        # the review record (review.REVIEWABLE)
        self.pane.show_file('src/rename_only.c', self.results['src/rename_only.c'],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()
        self.assertTrue(self.pane._stops)
        self.assertIsNone(self.pane.current_unit())
        self.assertTrue(self.pane.next_change())
        self.assertIsNone(self.pane.current_unit())

    def test_stepping_moves_the_gutter_arrow_on_both_panes(self):
        self.pane.first_change()
        first = frozenset(self.pane.old_edit._cur_rows)
        self.assertTrue(first)
        self.assertEqual(self.pane.old_edit._cur_rows, self.pane.new_edit._cur_rows)
        self.pane.next_change()
        self.assertTrue(self.pane.old_edit._cur_rows)
        self.assertNotEqual(self.pane.old_edit._cur_rows, first)

    def test_leaving_a_file_clears_the_arrow_it_left_behind(self):
        self.pane.first_change()
        self.assertTrue(self.pane.old_edit._cur_rows)
        # same.h has no hunks at all -- the marker from the previous file
        # must not still be sitting there once a file with nothing to mark
        # replaces it
        self.pane.show_file('src/same.h', self.results['src/same.h'],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()
        self.assertEqual(self.pane.old_edit._cur_rows, frozenset())
        self.assertEqual(self.pane.new_edit._cur_rows, frozenset())


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

    def test_comment_only_and_ignorable_only_files_are_walkable_by_default(self):
        # comment_only.c / admindata.arxml keep their noise verdict while the
        # matching checkbox is ticked (the default) -- F7/F8 must walk into
        # them too, not stop at real-change / added / deleted / error alone
        self.assertEqual(self.win.results['src/comment_only.c']['status'],
                         'comment-only')
        self.assertTrue(self.win._is_nav('src/comment_only.c'))
        self.assertEqual(self.win.results['arxml/admindata.arxml']['status'],
                         'ignorable-only')
        self.assertTrue(self.win._is_nav('arxml/admindata.arxml'))

    def test_unticking_a_rule_folds_its_files_out_of_the_walk(self):
        self.assertTrue(self.win._is_nav('src/comment_only.c'))
        self.win.cb_comment.setChecked(False)
        self._settle_ui()
        self.assertEqual(self.win.results['src/comment_only.c']['status'], 'identical')
        self.assertFalse(self.win._is_nav('src/comment_only.c'))

    def test_next_change_stops_inside_a_shown_comment_only_file_with_no_unit(self):
        nav = [r for r in self.win._tree_rels() if self.win._is_nav(r)]
        self.assertIn('src/comment_only.c', nav)
        self.win._reselect(nav[nav.index('src/comment_only.c') - 1])
        self._settle_ui()
        self.win._next_change()
        self._settle_ui()
        self.assertEqual(self.win._selected_rel(), 'src/comment_only.c')
        self.assertTrue(self.win.diff._stops)
        self.assertIsNone(self.win.diff.current_unit())

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


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestMutedCategories(unittest.TestCase):
    """Switching a noise category off greys its lines instead of removing them.

    Two claims have to hold together. The lines stay -- they are the context
    the surviving changes are read in, and a regenerated file is mostly banner
    churn, so dropping them left the real hunks floating. And they stop
    counting as changes everywhere that answers "where should I look next":
    the minimap and F7/F8.
    """

    REL = 'a2l/cal.a2l'  # one comment hunk and one real one

    def setUp(self):
        from compare_tool.qtviewer.diffpane import DiffPane
        self.app = _app()
        self.results = scan(FIX / 'old', FIX / 'new')
        self.pane = DiffPane()
        self.addCleanup(self.pane.deleteLater)

    def _show(self, muted=()):
        self.pane.set_muted_modes(muted)
        self.pane.show_file(self.REL, self.results[self.REL],
                            str(FIX / 'old'), str(FIX / 'new'))
        for _ in range(5):
            self.app.processEvents()
        return self.pane.rows

    def test_no_line_is_taken_away(self):
        plain = [(r.old_no, r.old_txt, r.new_no, r.new_txt) for r in self._show()]
        muted = [(r.old_no, r.old_txt, r.new_no, r.new_txt)
                 for r in self._show(('comment',))]
        self.assertEqual(muted, plain)

    def test_the_comment_rows_lose_their_diff_colour(self):
        from compare_tool import theme
        from compare_tool.view_model import MUTED
        rows = self._show()
        i = next(k for k, r in enumerate(rows) if r.mode == 'comment')
        doc = self.pane.old_edit.document()
        before = doc.findBlockByNumber(i).blockFormat().background().color().name()
        self.assertEqual(before, theme.c('del-bg-dim'))
        rows = self._show(('comment',))
        self.assertEqual(rows[i].mode, MUTED)
        doc = self.pane.old_edit.document()
        after = doc.findBlockByNumber(i).blockFormat().background().color().name()
        self.assertEqual(after, theme.c('muted-bg'))

    def test_a_muted_row_carries_no_inline_highlight(self):
        i = next(k for k, r in enumerate(self._show()) if r.mode == 'comment')
        self._show(('comment',))
        self.assertEqual(_backgrounds(self.pane.old_edit)[i], ['block'])

    def test_the_minimap_stops_marking_them_as_changes(self):
        self._show()
        with_noise = [k for k, r in enumerate(self.pane.minimap._rows)
                      if r.mode not in ('ctx', 'muted')]
        self._show(('comment',))
        without = [k for k, r in enumerate(self.pane.minimap._rows)
                   if r.mode not in ('ctx', 'muted')]
        self.assertLess(len(without), len(with_noise))
        self.assertTrue(without, 'the real change must still be on the map')

    def test_the_real_change_still_stops_where_it_did(self):
        # muting moves no row, so the real hunk's own stop needs no
        # translation -- this is the assertion that would catch it if one
        # ever did. Unmuted, the comment hunk is ALSO a stop now (shown noise
        # is navigable); muting it away removes that stop but leaves the real
        # one exactly where it was.
        self._show()
        unmuted = list(self.pane._stops)
        self._show(('comment', 'minor'))
        muted = list(self.pane._stops)
        self.assertTrue(muted)
        self.assertTrue(set(muted).issubset(unmuted))
        self.assertGreater(len(unmuted), len(muted))

    def test_a_real_change_is_never_muted(self):
        from compare_tool.view_model import MUTED
        rows = self._show(('real', 'moved', 'comment', 'minor'))
        self.assertIn('real', [r.mode for r in rows])
        self.assertNotIn(MUTED, [r.mode for r in rows if r.kind == 'real'])


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestThemeSwitch(unittest.TestCase):
    """The light theme has to reach every surface that stamps a colour in.

    Row backgrounds are block formats inside the document and tree colours are
    per item, so neither follows a stylesheet swap -- the failure mode is half
    a window in the old theme, which no assertion about the palette alone
    would catch.
    """

    def setUp(self):
        from compare_tool import theme
        from compare_tool.qtviewer.app import MainWindow
        self.theme = theme
        self.app = _app()
        self.addCleanup(theme.set_current, theme.DEFAULT)
        self.win = MainWindow(str(FIX / 'old'), str(FIX / 'new'))
        self.win.resize(1200, 800)
        self.win.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.win.show()
        self.addCleanup(self.win.close)
        _settle(self.app, self.win)

    def _settle_ui(self):
        for _ in range(5):
            self.app.processEvents()

    def _row_bgs(self):
        doc = self.win.diff.old_edit.document()
        return {doc.findBlockByNumber(i).blockFormat().background().color().name()
                for i in range(doc.blockCount())}

    def test_the_viewer_opens_in_the_theme_it_was_asked_for(self):
        from compare_tool.qtviewer.app import MainWindow
        win = MainWindow(str(FIX / 'old'), str(FIX / 'new'),
                         theme_name=self.theme.LIGHT)
        self.addCleanup(win.close)
        self.assertEqual(self.theme.current(), self.theme.LIGHT)

    def test_switching_repaints_the_diff_rows_not_just_the_chrome(self):
        self.win._reselect('src/real_change.c')
        self._settle_ui()
        dark = self._row_bgs()
        self.assertIn(self.theme.color('del-bg', self.theme.DARK), dark)
        self.win._set_theme(self.theme.LIGHT)
        self._settle_ui()
        light = self._row_bgs()
        self.assertIn(self.theme.color('del-bg', self.theme.LIGHT), light)
        self.assertNotIn(self.theme.color('del-bg', self.theme.DARK), light)

    def test_switching_repaints_the_tree_verdict_colours(self):
        def first_colour():
            item = self.win.tree.topLevelItem(0)
            return item.foreground(0).color().name()

        dark = first_colour()
        self.win._set_theme(self.theme.LIGHT)
        self._settle_ui()
        self.assertNotEqual(first_colour(), dark)

    def test_the_file_on_screen_survives_the_switch(self):
        self.win._reselect('src/real_change.c')
        self._settle_ui()
        self.win._set_theme(self.theme.LIGHT)
        self._settle_ui()
        self.assertEqual(self.win._selected_rel(), 'src/real_change.c')
        self.assertEqual(self.win.diff._rel, 'src/real_change.c')

    def test_the_change_being_read_survives_the_switch(self):
        # re-rendering the file parks on change 1; a colour switch is not a
        # navigation command, so the reviewer must come back to where they were
        self.win._reselect('src/rename_conflict.c')
        self._settle_ui()
        self.assertTrue(self.win.diff.next_change())
        self._settle_ui()
        row = self.win.diff._drive.textCursor().blockNumber()
        idx = self.win.diff._cur_idx
        self.assertGreater(idx, 0)
        self.win._set_theme(self.theme.LIGHT)
        self._settle_ui()
        self.assertEqual(self.win.diff._drive.textCursor().blockNumber(), row)
        self.assertEqual(self.win.diff._cur_idx, idx)

    def test_the_toggle_goes_back_and_forth(self):
        self.win._toggle_theme()
        self.assertEqual(self.theme.current(), self.theme.LIGHT)
        self.win._toggle_theme()
        self.assertEqual(self.theme.current(), self.theme.DARK)


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestFolderPickerStartDir(unittest.TestCase):
    """Browsing one side opens beside the other -- old/ and new/ are siblings,
    so the folder you are about to pick is right where the other side lives."""

    def setUp(self):
        from compare_tool.qtviewer.pickers import FolderPicker
        _app()
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.parent_dir = base / 'funcdemo'
        self.old = self.parent_dir / 'old'
        self.new = self.parent_dir / 'new'
        self.old.mkdir(parents=True)
        self.new.mkdir()
        self.FolderPicker = FolderPicker

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_side_starts_in_the_other_sides_parent(self):
        # BASELINE set, CURRENT empty -> browsing CURRENT opens in the parent
        # that holds both old/ and new/
        dlg = self.FolderPicker(None, old=str(self.old), new=None)
        self.assertEqual(dlg._start_dir(dlg.new_row), str(self.parent_dir))

    def test_it_is_symmetric(self):
        # CURRENT set, BASELINE empty -> same, from the other direction
        dlg = self.FolderPicker(None, old=None, new=str(self.new))
        self.assertEqual(dlg._start_dir(dlg.old_row), str(self.parent_dir))

    def test_a_side_with_its_own_path_stays_there(self):
        dlg = self.FolderPicker(None, old=str(self.old), new=str(self.new))
        self.assertEqual(dlg._start_dir(dlg.old_row), str(self.old))

    def test_a_zip_side_starts_in_the_zips_folder(self):
        # a side may hold a .zip; browsing the other opens where the zip lives
        zip_path = self.parent_dir / 'artifact.zip'
        zip_path.write_bytes(b'')
        dlg = self.FolderPicker(None, old=str(zip_path), new=None)
        self.assertEqual(dlg._start_dir(dlg.new_row), str(self.parent_dir))

    def test_both_empty_is_blank(self):
        dlg = self.FolderPicker(None, old=None, new=None)
        self.assertEqual(dlg._start_dir(dlg.old_row), '')


if __name__ == '__main__':
    unittest.main()
