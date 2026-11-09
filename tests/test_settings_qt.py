"""Exercise the viewer preferences at the dialog and CLI entry points."""

import os
from pathlib import Path
from string import Formatter
import tempfile
import unittest
from unittest import mock

from compare_tool import theme
from compare_tool import config as app_config
from compare_tool.messages import Message
from compare_tool.qtviewer.i18n import Texts
from compare_tool.qtviewer.vi import VI

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from compare_tool.qtviewer.app import MainWindow
    from compare_tool.qtviewer.dialogs import published_release_notes
    from compare_tool.qtviewer.settings import Preferences, SettingsDialog, YamlSettings, load_preferences
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

    def test_yaml_store_save_cancel_and_embedded_policy(self):
        path = Path(self.tmp.name) / 'settings.yaml'
        self.store = YamlSettings(path)
        before = path.read_bytes() if path.exists() else None
        win = self.window()
        self.edit_dialog(win, QDialogButtonBox.Cancel)
        self.assertEqual(path.read_bytes() if path.exists() else None, before)
        self.edit_dialog(win, QDialogButtonBox.Save)
        self.assertEqual(app_config.load(path)['appearance']['language'], 'vi')
        self.assertEqual(YamlSettings(path).value('language'), 'vi')
        self.assertEqual(win.code_check.policy_path, '')

    def test_cli_scan_overrides_are_the_settings_draft_and_stale_baseline(self):
        from compare_tool.main import main
        path = Path(self.tmp.name) / 'settings.yaml'
        app_config.save(path, app_config.defaults())
        rule_file = Path(self.tmp.name) / 'rules.json'
        rule_file.write_text('{"rules": [{"name": "stamp", "pattern": "STAMP_[0-9]+"}]}', encoding='utf-8')
        with mock.patch('compare_tool.qtviewer.run_viewer', return_value=0) as launch:
            self.assertEqual(main(['--qt', '--exclude', '*.c', '--skip-var-renames',
                                   '--rules', str(rule_file)]), 0)
        win = MainWindow(*launch.call_args.args, **launch.call_args.kwargs, settings=YamlSettings(path))
        self.addCleanup(win.close)
        self.assertEqual(app_config.load(path), app_config.defaults())
        win._raw_results = {'kept.h': {'status': 'identical'}}
        win.act_export.setEnabled(True)
        self.edit_dialog(win, QDialogButtonBox.Save)
        self.assertEqual(win.exclude, ('*.c',))
        self.assertTrue(win.skip_var_renames)
        self.assertEqual([rule.name for rule in win.user_rules], ['stamp'])
        self.assertEqual(app_config.load(path)['compare']['exclude'], ['*.c'])
        self.assertTrue(win.act_export.isEnabled())

        def change_scope(dialog):
            dialog.compare_exclude.clear()
            return 1

        with mock.patch.object(SettingsDialog, 'exec', change_scope):
            win.act_settings.trigger()
        self.assertEqual(win.exclude, ())
        self.assertEqual(win._raw_results, {})
        self.assertFalse(win.act_export.isEnabled())

    def test_explicit_negative_gui_flags_override_personal_config(self):
        from compare_tool.main import main
        path = Path(self.tmp.name) / 'settings.yaml'
        value = app_config.defaults()
        value['compare'].update(arxml_only=True, skip_var_renames=True, exclude=['*.c'])
        app_config.save(path, value)
        with mock.patch('compare_tool.qtviewer.run_viewer', return_value=0) as launch:
            self.assertEqual(main(['--qt', '--no-arxml-only', '--no-skip-var-renames', '--clear-exclude']), 0)
        win = MainWindow(*launch.call_args.args, **launch.call_args.kwargs, settings=YamlSettings(path))
        self.addCleanup(win.close)
        self.assertFalse(win.arxml_only)
        self.assertFalse(win.skip_var_renames)
        self.assertEqual(win.exclude, ())
        self.assertEqual(app_config.load(path), value)

    def test_scope_save_preserves_unreadable_settings_until_explicit_recovery(self):
        path = Path(self.tmp.name) / 'settings.yaml'
        original = b'schema_version: 999\ncompare:\n  exclude: [critical.c]\n'
        path.write_bytes(original)
        with mock.patch('compare_tool.config.settings_path', return_value=path):
            win = MainWindow()
        self.addCleanup(win.close)
        win.code_check.excludes.setPlainText('*.bak')
        win.code_check.save_defaults.click()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(win.code_check.defaults_status.text(), 'Code Check scope could not be saved.')

        dialog = SettingsDialog(win, win._prefs, win._text, config=win._config)
        with mock.patch('compare_tool.qtviewer.settings.QFileDialog.getSaveFileName',
                        return_value=(str(path), '')), mock.patch(
                            'compare_tool.qtviewer.settings.QMessageBox.warning') as warning:
            dialog._export_config()
        warning.assert_called_once()
        self.assertEqual(path.read_bytes(), original)

        def restore(dialog):
            dialog._restore_defaults()
            return 1

        with mock.patch.object(SettingsDialog, 'exec', restore):
            win.act_settings.trigger()
        self.assertEqual(app_config.load(path), app_config.defaults())
        win.code_check.excludes.setPlainText('*.bak')
        win.code_check.save_defaults.click()
        self.assertEqual(app_config.load(path)['code_check']['exclude'], ['*.bak'])

    def test_policy_editor_round_trip_lists_rules_mappings_and_exceptions(self):
        policy = app_config.defaults()['code_check']['policy']
        policy['forbidden_rte_prefixes'] = ['Rte_IRead_', 'Rte_Ω_']
        policy['ignore_rte_call_regex'] = [' Rte_Call_Test ']
        policy['rules']['orphan_access'] = 'skip'
        policy['function_mappings'] = [{
            'file': 'src/Ω.c', 'function': 'Run_Task',
            'runnable': '/Component/Run_Task', 'reason': 'Reviewed mapping',
        }]
        policy['exceptions'] = [{
            'rule': 'orphan_access', 'reason': 'Generated stub',
            'file': 'src/Ω.c', 'swc': '/Component',
        }]
        policy['no_rte_expected'] = 'Library-only code'
        config = app_config.defaults()
        config['code_check']['policy'] = policy
        dialog = SettingsDialog(None, Preferences(), Texts('en'), config=config)
        self.addCleanup(dialog.close)
        self.assertFalse(hasattr(dialog, 'policy_data'))
        self.assertEqual(dialog.policy_editor.policy(), policy)
        editor = dialog.policy_editor
        with mock.patch('compare_tool.qtviewer.policy_editor.QInputDialog.getText',
                        return_value=('Rte_New_', True)):
            editor._add_list_item('forbidden_rte_prefixes')
        self.assertEqual(editor.lists['forbidden_rte_prefixes'].count(), 3)
        editor.lists['forbidden_rte_prefixes'].setCurrentRow(2)
        editor._remove_list_item('forbidden_rte_prefixes')
        editor.lists['forbidden_rte_prefixes'].item(1).setText('Rte_Changed_')
        editor.rules['orphan_access'].setCurrentIndex(
            editor.rules['orphan_access'].findData('warn'))
        editor.mappings.item(0, 3).setText('Reviewed again')
        editor.exceptions.item(0, 1).setText('Known generated stub')
        updated = dialog.config()['code_check']['policy']
        self.assertEqual(updated['ignore_rte_call_regex'], [' Rte_Call_Test '])
        self.assertEqual(updated['forbidden_rte_prefixes'], ['Rte_IRead_', 'Rte_Changed_'])
        self.assertEqual(updated['rules']['orphan_access'], 'warn')
        self.assertEqual(updated['function_mappings'][0]['reason'], 'Reviewed again')
        self.assertEqual(updated['exceptions'][0]['reason'], 'Known generated stub')
        self.assertEqual(updated['exceptions'][0]['swc'], '/Component')
        self.assertEqual(updated['no_rte_expected'], 'Library-only code')
        editor._add_row(editor.exceptions, ('rule', 'reason', 'file', 'swc', 'runnable', 'port'))
        with self.assertRaises(ValueError):
            dialog.config()

    def test_policy_file_import_updates_editable_draft(self):
        path = Path(self.tmp.name) / 'policy.json'
        path.write_text('{"rules": {"orphan_access": "off"}, '
                        '"forbidden_functions": ["UnsafeCall"]}', encoding='utf-8')
        dialog = SettingsDialog(None, Preferences(), Texts('vi'))
        self.addCleanup(dialog.close)
        with mock.patch('compare_tool.qtviewer.settings.QFileDialog.getOpenFileName',
                        return_value=(str(path), '')):
            dialog._pick_policy()
        self.assertEqual(dialog.policy_editor.rules['orphan_access'].currentData(), 'off')
        self.assertEqual(dialog.policy_editor.lists['forbidden_functions'].item(0).text(),
                         'UnsafeCall')
        dialog.policy_editor.rules['orphan_access'].setCurrentIndex(
            dialog.policy_editor.rules['orphan_access'].findData('warn'))
        self.assertEqual(dialog.config()['code_check']['policy']['rules']['orphan_access'], 'warn')
        self.assertEqual(dialog.policy_editor.tabs.tabText(0), 'Mẫu và tên')

        bad = Path(self.tmp.name) / 'bad-policy.json'
        bad.write_text('{"rules": {"orphan_access": "invalid"}}', encoding='utf-8')
        before = dialog.policy_editor.policy()
        with mock.patch('compare_tool.qtviewer.settings.QFileDialog.getOpenFileName',
                        return_value=(str(bad), '')):
            with mock.patch('compare_tool.qtviewer.settings.QMessageBox.warning') as warning:
                dialog._pick_policy()
        warning.assert_called_once()
        self.assertEqual(dialog.policy_editor.policy(), before)

    def test_legacy_migration_embeds_policy_once(self):
        legacy = QSettings(str(Path(self.tmp.name) / 'legacy.ini'), QSettings.IniFormat)
        legacy.setValue('language', 'vi')
        policy = Path(self.tmp.name) / 'policy.yaml'
        policy.write_text('rules:\n  orphan_access: off\n', encoding='utf-8')
        legacy.setValue('code_check/defaults', {'config_path': str(policy),
                                                'excludes': '*.tmp', 'ignore_regex': ''})
        legacy.sync()
        destination = Path(self.tmp.name) / 'migrated.yaml'
        with mock.patch('compare_tool.qtviewer.settings.QSettings', return_value=legacy):
            store = YamlSettings(destination)
        self.assertEqual(store.config['appearance']['language'], 'vi')
        self.assertEqual(store.config['code_check']['exclude'], ['*.tmp'])
        self.assertEqual(store.config['code_check']['policy']['rules']['orphan_access'], 'off')
        self.assertTrue(destination.exists())

    def test_yaml_save_failure_keeps_applied_settings(self):
        path = Path(self.tmp.name) / 'settings.yaml'
        with mock.patch('compare_tool.qtviewer.settings.QSettings') as legacy:
            legacy.return_value.allKeys.return_value = []
            store = YamlSettings(path)
        old = store.config['appearance']['language']
        store.setValue('language', 'vi')
        with mock.patch('compare_tool.qtviewer.settings.app_config.save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                store.sync()
        self.assertEqual(store.config['appearance']['language'], old)

    def test_code_check_scope_has_one_editor_and_settings_keeps_run_override(self):
        path = Path(self.tmp.name) / 'settings.yaml'
        with mock.patch('compare_tool.qtviewer.settings.QSettings') as legacy:
            legacy.return_value.allKeys.return_value = []
            self.store = YamlSettings(path)
        win = self.window()
        win.code_check.excludes.setPlainText('session/*.c')
        win.code_check.ignore.setText('^Session_')
        dialog = SettingsDialog(win, win._prefs, win._text, config=win._config)
        self.addCleanup(dialog.close)
        self.assertFalse(hasattr(dialog, 'scope'))
        self.assertFalse(hasattr(dialog, 'ignore'))
        self.edit_dialog(win, QDialogButtonBox.Save)
        self.assertEqual(win.code_check.excludes.toPlainText(), 'session/*.c')
        self.assertEqual(win.code_check.ignore.text(), '^Session_')
        self.assertEqual(app_config.load(path)['code_check']['exclude'], [])
        win.code_check.save_defaults.click()
        self.assertEqual(win._config['code_check']['exclude'], ['session/*.c'])
        self.assertEqual(win._config['code_check']['ignore_regex'], '^Session_')

        imported = app_config.defaults()
        imported['code_check']['exclude'] = ['imported/*.h']
        imported['code_check']['ignore_regex'] = '^Imported_'

        def accept_import(dialog):
            dialog._load_fields(imported)
            dialog._replaced_config = True
            return 1  # QDialog.Accepted

        with mock.patch.object(SettingsDialog, 'exec', accept_import):
            win.act_settings.trigger()
        self.assertEqual(win.code_check.excludes.toPlainText(), 'imported/*.h')
        self.assertEqual(win.code_check.ignore.text(), '^Imported_')
        self.assertEqual(app_config.load(path)['code_check']['exclude'], ['imported/*.h'])

    def test_release_notes_show_only_dated_sections(self):
        changelog = ('# Changelog\n\n## [Unreleased]\n\nPending\n\n'
                     '## [2.0.0] — 2026-11-06\n\nPublished\n\n'
                     '## [0.4.0] and earlier\n\nUndated\n')
        self.assertEqual(published_release_notes(changelog),
                         '## [2.0.0] — 2026-11-06\n\nPublished')
