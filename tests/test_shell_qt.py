"""Application shell: menu bar, recent sources and the window-state sidecar."""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

from compare_tool import config as app_config
from compare_tool import theme

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication, QDialog

    from compare_tool.qtviewer.app import MainWindow
    from compare_tool.qtviewer.settings import SettingsDialog, YamlSettings
    from compare_tool.qtviewer.shell import (MAX_RECENT, STATE_FILE, WindowState,
                                             entry_available, folders_entry, git_entry)
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
            for _ in range(5):
                app.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError('scan did not finish within {}s'.format(timeout))


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestWindowState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_yaml_store_keeps_state_beside_settings_and_out_of_the_config(self):
        settings = self.dir / 'settings.yaml'
        app_config.save(settings, app_config.defaults())
        portable = settings.read_bytes()
        state = WindowState.for_store(YamlSettings(settings))
        self.assertEqual(state.path, self.dir / STATE_FILE)
        state.geometry = b'\x01\x02geometry'
        state.add_recent(folders_entry(self.dir / 'old', self.dir / 'new'))
        self.assertTrue(state.save())
        self.assertEqual(settings.read_bytes(), portable)  # no local paths in the portable config
        again = WindowState.for_store(YamlSettings(settings))
        self.assertEqual(again.geometry, b'\x01\x02geometry')
        self.assertEqual(again.recent, state.recent)
        self.assertEqual(again.error, '')

    def test_recent_is_newest_first_deduplicated_and_capped(self):
        state = WindowState()
        for n in range(MAX_RECENT + 3):
            state.add_recent(folders_entry(self.dir / 'old', self.dir / 'new{}'.format(n)))
        self.assertEqual(len(state.recent), MAX_RECENT)
        self.assertTrue(state.recent[0]['new'].endswith('new{}'.format(MAX_RECENT + 2)))
        again = folders_entry(self.dir / 'old', self.dir / 'new5')
        state.add_recent(again)
        self.assertEqual(state.recent[0], again)
        self.assertEqual(sum(e['new'] == again['new'] for e in state.recent), 1)
        state.add_recent(git_entry(self.dir, 'a' * 40, None))
        state.add_recent(git_entry(self.dir, 'a' * 40, 'b' * 40))  # another pair, kept apart
        self.assertEqual([e['kind'] for e in state.recent[:2]], ['git', 'git'])
        with self.assertRaises(ValueError):
            state.add_recent({'kind': 'folders', 'old': '', 'new': 'x'})

    def test_unreadable_state_starts_fresh_and_is_replaced_on_save(self):
        path = self.dir / STATE_FILE
        for raw in ('{not json', json.dumps({'version': 99}), json.dumps([1]),
                    json.dumps({'version': 1, 'recent': None}),
                    json.dumps({'version': 1, 'recent': 5}),
                    json.dumps({'version': 1, 'geometry': 'not base64!'})):
            path.write_text(raw, encoding='utf-8')
            state = WindowState(path)
            self.assertEqual((state.geometry, state.recent), (None, []))
            self.assertTrue(state.error)
        self.assertTrue(state.save())
        self.assertEqual(WindowState(path).error, '')

    def test_invalid_entries_are_dropped_valid_ones_kept(self):
        path = self.dir / STATE_FILE
        good = folders_entry(self.dir / 'a', self.dir / 'b')
        path.write_text(json.dumps({'version': 1, 'geometry': '', 'recent': [
            {'kind': 'svn', 'folder': 'x'}, {'kind': 'git', 'folder': 'x'}, 'text', good]}),
            encoding='utf-8')
        self.assertEqual(WindowState(path).recent, [good])

    def test_qsettings_and_memory_backends(self):
        store = QSettings(str(self.dir / 'viewer.ini'), QSettings.IniFormat)
        state = WindowState.for_store(store)
        state.add_recent(folders_entry('a', 'b'))
        self.assertTrue(state.save())
        self.assertEqual(WindowState.for_store(QSettings(str(self.dir / 'viewer.ini'),
                                                         QSettings.IniFormat)).recent, state.recent)
        memory = WindowState.for_store(Mock(value=lambda _key, default: default))
        memory.add_recent(folders_entry('a', 'b'))
        self.assertTrue(memory.save())
        self.assertIsNone(memory.path)

    def test_a_failed_save_reports_false_instead_of_raising(self):
        blocker = self.dir / STATE_FILE
        blocker.mkdir()  # a directory where the file should go
        state = WindowState(blocker)
        state.add_recent(folders_entry('a', 'b'))
        self.assertFalse(state.save())

    def test_missing_paths_make_an_entry_unavailable(self):
        (self.dir / 'old').mkdir()
        self.assertFalse(entry_available(folders_entry(self.dir / 'old', self.dir / 'gone')))
        (self.dir / 'gone').mkdir()
        self.assertTrue(entry_available(folders_entry(self.dir / 'old', self.dir / 'gone')))
        self.assertFalse(entry_available(git_entry(self.dir / 'nope', 'a' * 40, None)))


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestShellWindow(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.addCleanup(theme.set_current, theme.DEFAULT)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'settings.yaml'
        app_config.save(self.path, app_config.defaults())

    def window(self, *args, **kwargs):
        kwargs.setdefault('settings', YamlSettings(self.path))
        win = MainWindow(*args, **kwargs)
        win.setAttribute(Qt.WA_DontShowOnScreen, True)
        win.show()
        self.addCleanup(win.close)
        return win

    @staticmethod
    def menus(win):
        return [action.menu() for action in win.menuBar().actions()]

    def test_menu_bar_holds_every_command_in_order(self):
        win = self.window()
        file_, view, tools, settings, help_ = self.menus(win)
        self.assertEqual([m.title() for m in (file_, view, tools, settings, help_)],
                         ['File', 'View', 'Tools', 'Settings', 'Help'])
        self.assertEqual([a for a in file_.actions() if not a.isSeparator() and not a.menu()],
                         [win.act_open, win.act_git, win.act_export, win.act_quit])
        self.assertIs(next(a for a in file_.actions() if a.menu()).menu(), win.recent_menu)
        self.assertEqual([a for a in view.actions() if not a.isSeparator()],
                         [win.act_view_compare, win.act_view_check, win.act_hide_identical])
        self.assertEqual(tools.actions(), [win.act_arxml_tool])
        self.assertEqual([a.menu().title() for a in settings.actions() if a.menu()],
                         ['Language', 'Theme'])
        self.assertEqual([a for a in help_.actions() if not a.isSeparator()],
                         [win.act_guide, win.act_notes, win.act_about])
        # Comment and Unimportant are compare rules: they never sit in a menu
        for menu in self.menus(win):
            self.assertNotIn(win.show_comment, menu.actions())
            self.assertNotIn(win.show_unimportant, menu.actions())
        self.assertEqual({a.shortcut().toString() for a in (win.act_open, win.act_git, win.act_quit)},
                         {'Ctrl+O', 'Ctrl+G', 'Ctrl+Q'})

    def test_view_and_tools_switch_workspaces_and_keep_checks_in_sync(self):
        win = self.window()
        self.assertTrue(win.act_view_compare.isChecked())
        win.act_view_check.trigger()
        self.assertIs(win.modes.currentWidget(), win.code_check)
        self.assertFalse(win.act_view_compare.isChecked())
        win.act_arxml_tool.trigger()
        self.assertIs(win.modes.currentWidget(), win.arxml_handler)
        self.assertFalse(win.act_view_compare.isChecked() or win.act_view_check.isChecked())
        win.modes.setCurrentIndex(0)
        self.assertTrue(win.act_view_compare.isChecked())

    def test_language_from_menu_retranslates_and_saves_only_that_key(self):
        win = self.window(exclude=['*.launch'])
        language = next(a for a in win.language_group.actions() if a.data() == 'vi')
        language.trigger()
        self.assertEqual([m.title() for m in self.menus(win)],
                         ['File', 'Xem', 'Công cụ', 'Cài đặt', 'Trợ giúp'])
        self.assertTrue(language.isChecked())
        saved = app_config.load(self.path)
        self.assertEqual(saved['appearance']['language'], 'vi')
        self.assertEqual(saved['compare'], app_config.defaults()['compare'])  # launch override stays in memory
        self.assertEqual(win.exclude, ('*.launch',))

    def test_theme_override_survives_quick_toggles_until_a_theme_is_chosen(self):
        win = self.window(theme_name=theme.DARK)
        win.act_hide_identical.trigger()
        self.assertEqual(win._theme, theme.DARK)
        saved = app_config.load(self.path)
        self.assertEqual(saved['appearance']['theme'], theme.LIGHT)
        self.assertTrue(saved['display']['hide_identical'])
        dark = next(a for a in win.theme_group.actions() if a.data() == theme.DARK)
        self.assertTrue(dark.isChecked())
        dark.trigger()
        self.assertEqual(app_config.load(self.path)['appearance']['theme'], theme.DARK)
        next(a for a in win.theme_group.actions() if a.data() == theme.LIGHT).trigger()
        self.assertEqual(win._theme, theme.LIGHT)
        self.assertEqual(app_config.load(self.path)['appearance']['theme'], theme.LIGHT)

    def test_settings_menu_opens_the_dialog_on_the_matching_page(self):
        win = self.window()
        seen = []

        def record(dialog):
            seen.append(dialog.tabs.tabText(dialog.tabs.currentIndex()))
            return QDialog.Rejected

        with mock.patch.object(SettingsDialog, 'exec', record):
            for action in (win.act_settings, win.act_settings_check,
                           win.act_settings_compare, win.act_settings_report):
                action.trigger()
        self.assertEqual(seen, ['General', 'Code Check', 'Compare', 'Report'])
        dialog = SettingsDialog(win, win._prefs, win._text, config=win._config)
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(hasattr(dialog, 'hide_identical'))  # one home: View > Hide identical

    def test_opened_folders_are_remembered_and_open_again_from_recent(self):
        old, new = str(DEMO / 'old'), str(DEMO / 'new')
        first = self.window(old, new)
        _settle(self.app, first)
        self.assertEqual(first.window_state.recent, [folders_entry(old, new)])
        first.close()
        state = json.loads((self.path.parent / STATE_FILE).read_text(encoding='utf-8'))
        self.assertEqual(state['recent'], [folders_entry(old, new)])
        self.assertTrue(state['geometry'])

        missing = folders_entry(old, str(Path(self.tmp.name) / 'gone'))
        second = self.window()
        second.window_state.add_recent(missing)
        second._fill_recent_menu()
        entries = [a for a in second.recent_menu.actions()
                   if not a.isSeparator() and a is not second.act_clear_recent]
        self.assertEqual([a.text() for a in entries], ['old  →  gone', 'old  →  new'])
        self.assertEqual([a.isEnabled() for a in entries], [False, True])
        self.assertEqual(entries[1].toolTip(), '{}\n{}'.format(old, new))
        second.modes.setCurrentIndex(1)
        entries[1].trigger()
        _settle(self.app, second)
        self.assertIs(second.modes.currentWidget(), second.compare_page)
        self.assertEqual((second.old, second.new), (old, new))
        self.assertTrue(second._raw_results)
        second.act_clear_recent.trigger()
        self.assertEqual(second.window_state.recent, [])
        self.assertFalse(second.act_clear_recent.isEnabled())

    def test_temporary_sources_are_not_remembered(self):
        scratch = Path(self.tmp.name) / 'unpacked'
        for side in ('old', 'new'):
            shutil.copytree(DEMO / side, scratch / side)
        win = self.window(str(scratch / 'old'), str(scratch / 'new'), temporary_root=str(scratch))
        _settle(self.app, win)
        self.assertEqual(win.window_state.recent, [])

    def test_recent_entries_wait_while_a_task_runs(self):
        win = self.window()
        win.window_state.add_recent(folders_entry(str(DEMO / 'old'), str(DEMO / 'new')))
        win._git_worker = object()
        try:
            win._fill_recent_menu()
            entry = next(a for a in win.recent_menu.actions() if a.toolTip())
            self.assertFalse(entry.isEnabled())
            with mock.patch.object(win, '_start_scan') as scan:
                win._open_recent(win.window_state.recent[0])
            scan.assert_not_called()
        finally:
            win._git_worker = None

    def test_quit_saves_geometry_through_the_normal_close(self):
        win = self.window()
        win.resize(win.width() - 20, win.height() + 40)
        want = bytes(win.saveGeometry())
        win.act_quit.trigger()
        self.assertFalse(win.isVisible())
        self.assertEqual(WindowState(self.path.parent / STATE_FILE).geometry, want)
        # the offscreen screen clamps a restored size, so check the hand-over
        # rather than the pixels
        with mock.patch.object(MainWindow, 'restoreGeometry') as restore:
            self.window()
        self.assertEqual(bytes(restore.call_args.args[0]), want)


if __name__ == '__main__':
    unittest.main()
