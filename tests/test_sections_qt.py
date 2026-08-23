"""Collapsible panes in the viewer's left column.

Skipped when PySide6 is absent, like the other Qt tests, so the suite still
runs headless. What is pinned here is the behaviour a reviewer would notice:
a pane folds to its bar, comes back the size it was, and all three live in one
splitter so every one of them can be dragged.
"""
import os
import time
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:                                  # pragma: no cover
    HAVE_QT = False

FIX = Path(__file__).parent / 'fixtures'
_APP = None


def _app():
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _settle(app, win, timeout=30.0):
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


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestSectionWidget(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QLabel
        from compare_tool.qtviewer.section import Section
        _app()
        self.content = QLabel('body')
        self.sec = Section('FILES', self.content)

    def test_starts_expanded_with_its_content(self):
        self.assertTrue(self.sec.is_expanded())
        self.assertFalse(self.content.isHidden())

    def test_folding_hides_the_content_and_caps_the_height(self):
        self.sec.set_expanded(False)
        self.assertFalse(self.sec.is_expanded())
        self.assertTrue(self.content.isHidden())
        # capped at the bar, so the bar itself survives -- a pane the reviewer
        # folded must leave a way back in
        self.assertEqual(self.sec.maximumHeight(), self.sec.header_height())

    def test_unfolding_lifts_the_cap_again(self):
        self.sec.set_expanded(False)
        self.sec.set_expanded(True)
        self.assertFalse(self.content.isHidden())
        self.assertGreater(self.sec.maximumHeight(), self.sec.header_height())

    def test_the_bar_says_which_way_it_is(self):
        self.sec.set_expanded(True)
        self.assertIn('FILES', self.sec.header.text())
        open_mark = self.sec.header.text()[0]
        self.sec.set_expanded(False)
        self.assertNotEqual(self.sec.header.text()[0], open_mark)

    def test_suffix_rides_along_on_the_bar(self):
        # a folded pane still has to be able to say it holds something
        self.sec.set_suffix('2 heads-ups')
        self.sec.set_expanded(False)
        self.assertIn('2 heads-ups', self.sec.header.text())


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestLeftColumnSections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from compare_tool.qtviewer.app import MainWindow, apply_theme
        cls.app = _app()
        apply_theme(cls.app)          # the QSS the real entry point applies
        demo = FIX / 'demo'
        cls.win = MainWindow(str(demo / 'old'), str(demo / 'new'))
        cls.win.resize(1400, 900)
        cls.win.show()
        _settle(cls.app, cls.win)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def setUp(self):
        for sec in self.win._sections:
            sec.set_expanded(True)
        self.win.left_split.setSizes([460, 230, 120])
        self._settle_ui()

    def _settle_ui(self):
        for _ in range(40):
            self.app.processEvents()

    def test_all_three_panes_share_one_splitter(self):
        # the advisories used to be pinned outside it, which is exactly why
        # that pane -- the one whose length is least predictable -- was the one
        # that could not be resized
        self.assertEqual(self.win.left_split.count(), 3)
        self.assertEqual(len(self.win.left_split.sizes()), 3)
        for sec in self.win._sections:
            self.assertIs(sec.parent(), self.win.left_split)

    def test_folding_a_pane_gives_its_height_to_the_others(self):
        before = self.win.left_split.sizes()
        self.win.sec_changes.header.click()
        self._settle_ui()
        after = self.win.left_split.sizes()
        self.assertEqual(after[1], self.win.sec_changes.header_height())
        self.assertGreater(after[0] + after[2], before[0] + before[2])
        self.assertEqual(sum(after), sum(before))

    def test_a_pane_comes_back_the_size_it_was(self):
        want = self.win.left_split.sizes()[1]
        self.win.sec_changes.header.click()     # fold
        self._settle_ui()
        self.win.sec_changes.header.click()     # and back
        self._settle_ui()
        # within a pixel or two of where the reviewer had left it -- folding a
        # pane to read something else is not them resizing it
        self.assertAlmostEqual(self.win.left_split.sizes()[1], want, delta=4)

    def test_folding_the_tree_leaves_its_bar_behind(self):
        self.win.sec_files.header.click()
        self._settle_ui()
        # the tree is inside the section's content widget, so it is the
        # content that gets hidden -- isVisible() is what a reviewer sees
        self.assertFalse(self.win.tree.isVisible())
        self.assertEqual(self.win.left_split.sizes()[0],
                         self.win.sec_files.header_height())
        self.win.sec_files.header.click()
        self._settle_ui()
        self.assertTrue(self.win.tree.isVisible())

    def test_folding_everything_stacks_the_bars_at_the_top(self):
        # left alone Qt centres a splitter shorter than the space it is given,
        # which left the three bars adrift halfway down an empty panel
        for sec in self.win._sections:
            if sec.is_expanded():
                sec.header.click()
        self._settle_ui()
        tops = [sec.mapTo(self.win.left_split, sec.rect().topLeft()).y()
                for sec in self.win._sections if sec.isVisible()]
        self.assertEqual(tops[0], 0)
        self.assertEqual(tops, sorted(tops))
        # and the splitter itself is capped, so it cannot claim the empty space
        self.assertLess(self.win.left_split.maximumHeight(), 200)

    def test_opening_one_again_lets_the_column_fill(self):
        for sec in self.win._sections:
            if sec.is_expanded():
                sec.header.click()
        self._settle_ui()
        self.win.sec_files.header.click()
        self._settle_ui()
        self.assertGreater(self.win.left_split.maximumHeight(), 1000)
        self.assertTrue(self.win.tree.isVisible())

    def test_the_rule_checkboxes_live_inside_the_files_pane(self):
        # they used to float above all three panes, which left them stranded
        # mid-panel once every pane was folded
        self.assertTrue(self.win.cb_comment.isVisible())
        self.win.sec_files.header.click()
        self._settle_ui()
        self.assertFalse(self.win.cb_comment.isVisible())
        self.assertFalse(self.win.cb_hide_identical.isVisible())

    def test_consistency_pane_carries_the_count_on_its_bar(self):
        # this fixture has two, and the bar has to say so even folded
        self.assertFalse(self.win.sec_consistency.isHidden())
        self.assertIn('2 heads-ups', self.win.sec_consistency.header.text())

    def test_one_heads_up_reads_singular_on_the_bar(self):
        self.win._show_advisories([('Ctrl', 'gained an RTE access')])
        self._settle_ui()
        text = self.win.sec_consistency.header.text()
        self.assertIn('1 heads-up', text)
        self.assertNotIn('heads-ups', text)

    def test_the_consistency_pane_goes_away_when_there_is_nothing_to_say(self):
        self.win._show_advisories(())
        self._settle_ui()
        self.assertTrue(self.win.sec_consistency.isHidden())


if __name__ == '__main__':
    unittest.main()
