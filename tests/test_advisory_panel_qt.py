"""Consistency advisory panel (viewer bottom-left).

Skipped when PySide6 is absent, so the rest of the suite still runs headless
(see the "viewer logic that can be Qt-free must be Qt-free" rule). The advisory
TEXT is computed Qt-free in compare_tool.consistency and covered there; this file
only checks the widget shows/hides it and the window wires it to the raw scan.
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
class TestAdvisoryPanel(unittest.TestCase):
    def setUp(self):
        from compare_tool.qtviewer.advisories import AdvisoryPanel
        _app()
        self.panel = AdvisoryPanel()

    def test_empty_is_hidden(self):
        self.panel.set_advisories([])
        self.assertFalse(self.panel.isVisible())

    def test_populated_is_visible_and_counts(self):
        self.panel.set_advisories([('Ctrl', 'gained an RTE access'),
                                   ('Brake', 'ARXML changed but the C did not')])
        # QWidget.isVisible() is False until shown, but isVisibleTo(parent) and
        # the non-hidden flag both report the intent set here
        self.assertFalse(self.panel.isHidden())
        self.assertIn('2 heads-ups', self.panel._header.text())
        body = self.panel._body.text()
        self.assertIn('Ctrl', body)
        self.assertIn('Brake', body)

    def test_singular_header(self):
        self.panel.set_advisories([('Ctrl', 'gained an RTE access')])
        self.assertIn('1 heads-up', self.panel._header.text())
        self.assertNotIn('heads-ups', self.panel._header.text())

    def test_html_in_message_is_escaped(self):
        self.panel.set_advisories([('A<b>', 'x & y <z>')])
        body = self.panel._body.text()
        self.assertIn('A&lt;b&gt;', body)
        self.assertIn('x &amp; y &lt;z&gt;', body)

    def test_clearing_hides_again(self):
        self.panel.set_advisories([('Ctrl', 'gained an RTE access')])
        self.panel.set_advisories(())
        self.assertTrue(self.panel.isHidden())


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestWindowWiresAdvisories(unittest.TestCase):
    def test_demo_scan_shows_both_advisories(self):
        from compare_tool.qtviewer.app import MainWindow
        app = _app()
        demo = FIX / 'demo'
        win = MainWindow(str(demo / 'old'), str(demo / 'new'))
        try:
            _settle(app, win)
            self.assertFalse(win.advisories.isHidden())
            models = [m for m, _msg in win.advisories._advisories]
            # the same list the report and CLI produce for this fixture
            self.assertEqual(set(models), {'StaleGen', 'Ctrl'})
        finally:
            win.close()


if __name__ == '__main__':
    unittest.main()
