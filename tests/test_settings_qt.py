"""Exercise the viewer preferences at the dialog and CLI entry points."""

import os
from pathlib import Path
from string import Formatter
import tempfile
import unittest
from unittest import mock

from compare_tool import theme
from compare_tool.messages import Message
from compare_tool.qtviewer.i18n import Texts
from compare_tool.qtviewer.vi import VI

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from compare_tool.qtviewer.app import MainWindow
    from compare_tool.qtviewer.dialogs import published_release_notes
    from compare_tool.qtviewer.settings import Preferences, SettingsDialog, load_preferences
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


class TestCatalog(unittest.TestCase):
    def test_placeholders_match_and_nested_templates_preserve_technical_values(self):
        def fields(template):
            return [field for _, field, _, _ in Formatter().parse(template) if field is not None]

        for en, vi in VI.items():
            with self.subTest(en=en):
                self.assertEqual(fields(en), fields(vi))
        detail = Message('{} Pattern: {}',
                         Message('The API matches ignore_rte_call_regex.'), '^Rte_Call_{Foo}')
        self.assertEqual(Texts('en')(detail), str(detail))
        self.assertEqual(Texts('vi')(detail),
                         'API khớp ignore_rte_call_regex. Mẫu regex: ^Rte_Call_{Foo}')


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'settings.ini')
        self.store = QSettings(self.path, QSettings.IniFormat)

    def window(self, theme_name=None):
        win = MainWindow(theme_name=theme_name, settings=self.store)
        win.show()
        self.addCleanup(win.close)
        return win

    def edit_dialog(self, win, button, policy=None):
        def edit():
            dlg = QApplication.activeModalWidget()
            dlg.language.setCurrentIndex(dlg.language.findData('vi'))
            dlg.theme.setCurrentIndex(dlg.theme.findData(theme.DARK))
            dlg.comment.setChecked(False)
            dlg.unimportant.setChecked(False)
            dlg.hide_identical.setChecked(True)
            if policy is not None:
                dlg.policy.setText(policy)
            dlg.buttons.button(button).click()

        QTimer.singleShot(0, edit)
        win.act_settings.trigger()

    def test_default_save_cancel_reload_and_cli_override(self):
        win = self.window()
        self.assertEqual(win._prefs, Preferences())
        self.assertEqual(win._theme, theme.LIGHT)
        self.assertEqual(win.act_settings.text(), 'Settings')

        self.edit_dialog(win, QDialogButtonBox.Cancel)
        self.assertEqual(win._prefs, Preferences())
        self.assertEqual(self.store.allKeys(), [])
        self.edit_dialog(win, QDialogButtonBox.Save)
        self.assertEqual(win.act_settings.text(), 'Cài đặt')
        self.assertEqual(win.modes.tabText(0), 'So sánh')
        self.assertEqual(win._prefs, Preferences('vi', theme.DARK, False, False, True))
        self.assertEqual(win._theme, theme.DARK)
        win.close()

        self.store = QSettings(self.path, QSettings.IniFormat)
        reopened = self.window()
        self.assertEqual(reopened._prefs, win._prefs)
        self.assertEqual(reopened._theme, theme.DARK)
        reopened.close()
        override = self.window(theme.LIGHT)
        self.assertEqual(override._theme, theme.LIGHT)
        self.assertEqual(load_preferences(self.store).theme, theme.DARK)

    def test_invalid_settings_fall_back_to_defaults(self):
        for key in Preferences._fields:
            self.store.setValue(key, 'unrecognized')
        self.assertEqual(self.window()._prefs, Preferences())

    def test_settings_is_shared_by_both_workspaces(self):
        win = self.window()
        win.modes.setCurrentIndex(1)
        self.edit_dialog(win, QDialogButtonBox.Save)
        self.assertIs(win.modes.currentWidget(), win.code_check)
        dialog = SettingsDialog(win, win._prefs, win._text)
        self.assertEqual(dialog.windowTitle(), 'Cài đặt')
        self.assertEqual(dialog.buttons.button(QDialogButtonBox.Save).text(), 'Lưu')

    def test_policy_path_is_saved_only_when_settings_are_accepted(self):
        win = self.window()
        policy = str(Path(self.tmp.name) / 'policy.yaml')
        self.edit_dialog(win, QDialogButtonBox.Cancel, policy)
        self.assertEqual(win.code_check.policy_path, '')
        self.assertEqual(self.store.allKeys(), [])
        self.edit_dialog(win, QDialogButtonBox.Save, policy)
        self.assertEqual(win.code_check.policy_path, policy)
        self.assertEqual(self.window().code_check.policy_path, policy)

    def test_cli_passes_only_explicit_theme_to_viewer(self):
        from compare_tool.main import main
        with mock.patch('compare_tool.qtviewer.run_viewer', return_value=0) as launch:
            self.assertEqual(main(['--qt']), 0)
            self.assertIsNone(launch.call_args.kwargs['theme_name'])
            self.assertEqual(main(['--qt', '--theme', 'dark']), 0)
            self.assertEqual(launch.call_args.kwargs['theme_name'], 'dark')

    def test_release_notes_show_only_dated_sections(self):
        changelog = ('# Changelog\n\n## [Unreleased]\n\nPending\n\n'
                     '## [2.0.0] — 2026-11-06\n\nPublished\n\n'
                     '## [0.4.0] and earlier\n\nUndated\n')
        self.assertEqual(published_release_notes(changelog),
                         '## [2.0.0] — 2026-11-06\n\nPublished')
