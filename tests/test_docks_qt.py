"""One workspace: Compare and Code Check views, their dock panels and saved layouts."""

import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from compare_tool import config as app_config

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication, QStackedWidget

    from compare_tool.qtviewer.app import MainWindow, apply_theme
    from compare_tool.qtviewer.settings import YamlSettings
    from compare_tool.qtviewer.shell import STATE_FILE, WindowState
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

DEMO = Path(__file__).parent / 'fixtures' / 'demo'


def _app():
    return QApplication.instance() or QApplication([])


def _settle(app, win, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if win._raw_results and not (win.worker and win.worker.isRunning()):
            for _ in range(10):
                app.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError('scan did not finish within {}s'.format(timeout))


def _shown(docks):
    return [d.objectName() for d in docks if d.isVisible()]


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestWorkspaceDocks(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        apply_theme(self.app)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'settings.yaml'
        app_config.save(self.path, app_config.defaults())

    def window(self, *args, settings=None, scan=True):
        win = MainWindow(*args, settings=settings or YamlSettings(self.path))
        win.resize(1400, 900)
        win.setAttribute(Qt.WA_DontShowOnScreen, True)
        win.show()
        self.addCleanup(win.close)
        if scan and args:
            _settle(self.app, win)
        return win

    def demo(self, **kwargs):
        return self.window(str(DEMO / 'old'), str(DEMO / 'new'), **kwargs)

    def test_one_workspace_with_a_view_switch_and_no_tab_widget(self):
        win = self.window()
        self.assertIsInstance(win.views, QStackedWidget)
        self.assertEqual([win.views.widget(i) for i in range(2)], [win.compare_page, win.code_check])
        self.assertEqual([win.view_tabs.tabText(i) for i in range(2)], ['Compare', 'Code Check'])
        self.assertIs(win.centralWidget(), win.views)
        self.assertIsNone(importlib.util.find_spec('compare_tool.qtviewer.section'))
        win.view_tabs.setCurrentIndex(1)
        self.assertIs(win.views.currentWidget(), win.code_check)
        self.assertTrue(win.act_view_check.isChecked())
        win.act_view_compare.trigger()
        self.assertEqual(win.view_tabs.currentIndex(), 0)

    def test_each_view_brings_its_own_panels(self):
        win = self.demo()
        self.assertEqual(_shown(win.docks), ['filesDock', 'changesDock', 'advisoriesDock'])
        win._show_workspace(1)
        self.assertEqual(_shown(win.docks), ['checkSetupDock', 'evidenceDock', 'fixDock'])
        self.assertTrue(win.code_check.run_button.isVisible())
        win._show_workspace(0)
        self.assertEqual(_shown(win.docks), ['filesDock', 'changesDock', 'advisoriesDock'])

    def test_a_view_keeps_the_layout_the_reviewer_left_it_in(self):
        win = self.demo()
        win.changes_dock.close()
        win.evidence_dock.show()   # a Code Check panel beside the diff
        win._show_workspace(1)
        win.fix_dock.close()
        win._show_workspace(0)
        self.assertEqual(_shown(win.docks), ['filesDock', 'advisoriesDock', 'evidenceDock'])
        win._show_workspace(1)
        self.assertEqual(_shown(win.docks), ['checkSetupDock', 'evidenceDock'])
        win.act_reset_layout.trigger()
        self.assertEqual(_shown(win.docks), ['checkSetupDock', 'evidenceDock', 'fixDock'])

    def test_reset_puts_moved_tabbed_and_floating_panels_back(self):
        win = self.demo()
        win._show_workspace(1)
        win.addDockWidget(Qt.LeftDockWidgetArea, win.evidence_dock)
        win.tabifyDockWidget(win.setup_dock, win.evidence_dock)
        win.fix_dock.setFloating(True)
        win.act_reset_layout.trigger()
        self.assertEqual(win.dockWidgetArea(win.evidence_dock), Qt.RightDockWidgetArea)
        self.assertEqual(win.dockWidgetArea(win.fix_dock), Qt.BottomDockWidgetArea)
        self.assertEqual(win.tabifiedDockWidgets(win.setup_dock), [])
        self.assertFalse(win.fix_dock.isFloating())
        self.assertEqual(_shown(win.docks), ['checkSetupDock', 'evidenceDock', 'fixDock'])
        # a view opened for the first time starts from the built arrangement too
        win.addDockWidget(Qt.RightDockWidgetArea, win.files_dock)
        win._layouts.pop(0, None)
        win._show_workspace(0)
        self.assertEqual(win.dockWidgetArea(win.files_dock), Qt.LeftDockWidgetArea)

    def test_view_menu_lists_every_panel_and_reset(self):
        win = self.window()
        view = win.menuBar().actions()[1].menu()
        actions = view.actions()
        for dock in win.docks:
            self.assertIn(dock.toggleViewAction(), actions)
        self.assertIn(win.act_reset_layout, actions)
        self.assertEqual([d.windowTitle() for d in win.docks],
                         ['Files', 'Quick changes', 'Regeneration advisories',
                          'Check setup', 'Evidence', 'Suggested fix'])
        win._choose_language('vi')
        self.assertEqual(win.files_dock.windowTitle(), 'Cây file')
        self.assertEqual(win.advisories_dock.windowTitle(), 'Lưu ý regeneration')

    def test_the_files_panel_keeps_the_compare_rules_under_its_tree(self):
        win = self.demo()
        self.assertTrue(win.files_dock.isAncestorOf(win.tree))
        self.assertTrue(win.files_dock.isAncestorOf(win.compare_toolbar))
        tree_bottom = win.tree.mapTo(win, QPoint(0, win.tree.height())).y()
        self.assertLessEqual(tree_bottom, win.compare_toolbar.mapTo(win, QPoint(0, 0)).y())

    def test_advisories_carry_their_count_and_leave_when_empty(self):
        win = self.demo()
        self.assertTrue(win.advisories_dock.isVisible())
        self.assertIn('2 heads-ups', win.advisories_dock.windowTitle())
        win._show_advisories([('Ctrl', 'gained an RTE access')])
        self.assertIn('1 heads-up', win.advisories_dock.windowTitle())
        self.assertNotIn('heads-ups', win.advisories_dock.windowTitle())
        win._show_advisories(())
        self.assertFalse(win.advisories_dock.isVisible())
        self.assertEqual(win.advisories_dock.windowTitle(), 'Regeneration advisories')
        # a closed advisories panel stays closed while it still has advisories
        win._show_advisories([('Ctrl', 'x')])
        win.advisories_dock.close()
        win._show_advisories([('Ctrl', 'x'), ('Pedal', 'y')])
        self.assertFalse(win.advisories_dock.isVisible())

    def test_layouts_survive_a_restart_per_view(self):
        first = self.demo()
        first.changes_dock.close()
        first._show_workspace(1)
        first.evidence_dock.close()
        first.close()
        state = WindowState(self.path.parent / STATE_FILE)
        self.assertEqual(set(state.layouts), {'compare', 'check'})
        second = self.demo()
        self.assertEqual(_shown(second.docks), ['filesDock', 'advisoriesDock'])
        second._show_workspace(1)
        self.assertEqual(_shown(second.docks), ['checkSetupDock', 'fixDock'])

    def test_an_arxml_write_disables_the_compare_panels(self):
        win = self.window(settings=Mock(value=lambda _key, default: default))
        win.arxml_handler.panel.writing = True
        try:
            win._arxml_activity_changed()
            self.assertFalse(win.compare_page.isEnabled())
            self.assertFalse(win.files_dock.widget().isEnabled())
            self.assertFalse(win.code_check.setup_panel.isEnabled())
        finally:
            win.arxml_handler.panel.writing = False
            win._arxml_activity_changed()
        self.assertTrue(win.files_dock.widget().isEnabled())
        self.assertTrue(win.code_check.setup_panel.isEnabled())


if __name__ == '__main__':
    unittest.main()
