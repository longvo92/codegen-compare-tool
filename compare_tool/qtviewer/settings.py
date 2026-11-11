"""Preferences for the viewer, and the single dialog that edits them."""

from os.path import abspath
import json
from copy import deepcopy
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from .. import theme
from .. import config as app_config
from ..consistency import load_checker_config
from ..userrules import read_items
from .icons import app_icon
from .policy_editor import PolicyEditor


class Preferences(NamedTuple):
    language: str = 'en'
    theme: str = theme.LIGHT
    comment: bool = True
    unimportant: bool = True
    hide_identical: bool = False


class CodeCheckDefaults(NamedTuple):
    config_path: str = ''
    excludes: str = ''
    ignore_regex: str = ''


_CODE_CHECK_DEFAULTS_KEY = 'code_check/defaults'
_RECOVERY_REQUIRED = 'Import a valid config or restore defaults before saving.'


class YamlSettings:
    """QSettings-compatible narrow adapter for existing viewer callers."""

    def __init__(self, path=None, *, recovering=False):
        self.path = app_config.settings_path() if path is None else path
        self.recovering = recovering
        if recovering:
            self.config = app_config.defaults()
        else:
            self.config = app_config.load(self.path) if self.path.exists() else self._migrate()
        self._pending = None

    def _migrate(self):
        old = QSettings('CodeGenInspector', 'CodeGen Inspector')
        config = app_config.defaults()
        if not old.allKeys():
            return config
        prefs = load_preferences(old)
        config['appearance'].update(language=prefs.language, theme=prefs.theme)
        config['display'].update(comment=prefs.comment, unimportant=prefs.unimportant,
                                 hide_identical=prefs.hide_identical)
        previous = load_code_check_defaults(old)
        config['code_check'].update(exclude=[line.strip() for line in previous.excludes.splitlines()
                                             if line.strip()], ignore_regex=previous.ignore_regex)
        if previous.config_path:
            config['code_check']['policy'] = load_checker_config(previous.config_path)
        app_config.save(self.path, config)
        return config

    def value(self, key, fallback=None):
        if key == _CODE_CHECK_DEFAULTS_KEY:
            check = self.config['code_check']
            return {'config_path': '', 'excludes': '\n'.join(check['exclude']),
                    'ignore_regex': check['ignore_regex']}
        if key in ('language', 'theme'):
            return self.config['appearance'][key]
        return self.config['display'].get(key, fallback)

    def setValue(self, key, value):
        if self._pending is None:
            self._pending = deepcopy(self.config)
        target = self._pending
        if key == _CODE_CHECK_DEFAULTS_KEY:
            target['code_check']['exclude'] = [v.strip() for v in value['excludes'].splitlines() if v.strip()]
            target['code_check']['ignore_regex'] = value['ignore_regex']
            if value.get('config_path'):
                target['code_check']['policy'] = load_checker_config(value['config_path'])
        elif key in ('language', 'theme'):
            target['appearance'][key] = value
        else:
            target['display'][key] = value

    def sync(self):
        if self._pending is not None:
            try:
                self.save(self._pending)
            except Exception:
                self._pending = None
                raise
            # Keep the shared config object live for an already-open MainWindow.
            self.config.clear()
            self.config.update(self._pending)
            self._pending = None

    def save(self, value, *, recover=False):
        if self.recovering and not recover:
            raise ValueError(_RECOVERY_REQUIRED)
        app_config.save(self.path, value)
        self.recovering = False

    def status(self):
        return QSettings.Status.NoError


def preference_store():
    return YamlSettings()


def load_preferences(store):
    default = Preferences()

    def choice(key, choices, fallback):
        value = store.value(key, fallback)
        return value if value in choices else fallback

    def flag(key, fallback):
        value = store.value(key, fallback)
        return {'true': True, 'false': False}.get(str(value).lower(), fallback)

    return Preferences(choice('language', ('en', 'vi'), default.language),
                       choice('theme', theme.THEMES, default.theme),
                       flag('comment', default.comment),
                       flag('unimportant', default.unimportant),
                       flag('hide_identical', default.hide_identical))


def save_preferences(store, prefs):
    return _save_values(store, prefs._asdict())


def save_compare_visibility(store, prefs):
    """Persist the Compare toolbar choices without saving launch overrides."""
    values = {'comment': prefs.comment, 'unimportant': prefs.unimportant}
    if isinstance(store, YamlSettings):
        try:
            config = app_config.load(store.path) if store.path.exists() else app_config.defaults()
            config['display'].update(values)
            store.save(config)
        except (OSError, UnicodeError, ValueError):
            return False
        store.config['display'].update(values)
        return True
    return _save_values(store, values)


def _save_values(store, values):
    for key, value in values.items():
        store.setValue(key, value)
    try:
        store.sync()
    except (OSError, UnicodeError, ValueError):
        return False
    return store.status() == QSettings.Status.NoError


def load_code_check_defaults(store):
    values = store.value(_CODE_CHECK_DEFAULTS_KEY, {})
    if not isinstance(values, dict):
        return CodeCheckDefaults()
    return CodeCheckDefaults(**{key: values[key] for key in CodeCheckDefaults._fields
                                if isinstance(values.get(key), str)})


def save_code_check_defaults(store, defaults):
    try:
        store.setValue(_CODE_CHECK_DEFAULTS_KEY, dict(defaults._asdict()))
        store.sync()
    except (OSError, UnicodeError, ValueError):
        return False
    return store.status() == QSettings.Status.NoError


class SettingsDialog(QDialog):
    def __init__(self, parent, prefs, texts, *, policy_path='', config=None):
        super().__init__(parent)
        self._text = tr = texts
        self._replaced_config = False
        self.setObjectName('viewerSettings')
        self.setWindowTitle(tr('Settings'))
        self.setWindowIcon(app_icon())
        layout = QVBoxLayout(self)

        self._config = deepcopy(config or app_config.defaults())
        self._config['display'].update(comment=prefs.comment, unimportant=prefs.unimportant)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        general = QWidget()
        general_layout = QVBoxLayout(general)
        self.tabs.addTab(general, tr('General'))
        if parent is not None and hasattr(parent, '_settings') and hasattr(parent._settings, 'path'):
            general_layout.addWidget(QLabel('{}: {}'.format(tr('Settings file'), parent._settings.path)))
        appearance = QGroupBox(tr('Appearance'))
        form = QFormLayout(appearance)
        self.language = QComboBox()
        self.language.addItem('English', 'en')
        self.language.addItem('Tiếng Việt', 'vi')
        self.language.setCurrentIndex(self.language.findData(prefs.language))
        self.theme = QComboBox()
        self.theme.addItem(tr('Light'), theme.LIGHT)
        self.theme.addItem(tr('Dark'), theme.DARK)
        self.theme.setCurrentIndex(self.theme.findData(prefs.theme))
        for key, combo in (('Language', self.language), ('Theme', self.theme)):
            label = QLabel(tr(key))
            label.setBuddy(combo)
            combo.setAccessibleName(label.text())
            form.addRow(label, combo)
        general_layout.addWidget(appearance)

        display = QGroupBox(tr('Compare display'))
        options = QVBoxLayout(display)
        self.hide_identical = QCheckBox(tr('Hide identical'))
        self.hide_identical.setToolTip(tr('Hide only Identical files in the tree.'))
        self.hide_identical.setChecked(prefs.hide_identical)
        options.addWidget(self.hide_identical)
        general_layout.addWidget(display)

        policy = QGroupBox(tr('Code Check policy'))
        policy_layout = QVBoxLayout(policy)
        label = QLabel(tr('Import policy file (optional YAML / JSON)'))
        self.policy = QLineEdit(policy_path)
        self.policy.setPlaceholderText(tr('Select a policy file to import'))
        self.policy.setClearButtonEnabled(True)
        label.setBuddy(self.policy)
        browse = QPushButton(tr('Choose config…'))
        browse.clicked.connect(self._pick_policy)
        if config is not None:
            label.hide()
            self.policy.hide()
            browse.setText(tr('Import policy file…'))
        row = QHBoxLayout()
        row.addWidget(self.policy, 1)
        row.addWidget(browse)
        policy_layout.addWidget(label)
        policy_layout.addLayout(row)
        code_tab = QWidget()
        code_layout = QVBoxLayout(code_tab)
        code_layout.addWidget(policy)
        self.policy_editor = PolicyEditor(tr)
        self.policy_editor.set_policy(self._config['code_check']['policy'])
        code_layout.addWidget(self.policy_editor)
        self.tabs.addTab(code_tab, tr('Code Check'))

        compare_tab = QWidget()
        compare_layout = QVBoxLayout(compare_tab)
        self.compare_exclude = QPlainTextEdit('\n'.join(self._config['compare']['exclude']))
        self.compare_exclude.setPlaceholderText(tr('Excluded globs, one per line'))
        compare_layout.addWidget(QLabel(tr('Compare exclusions')))
        compare_layout.addWidget(self.compare_exclude)
        self.arxml_only = QCheckBox(tr('ARXML only'))
        self.skip_renames = QCheckBox(tr('Skip variable renames'))
        self.check_consistency = QCheckBox(tr('Check consistency'))
        self.exit_zero = QCheckBox(tr('Exit zero'))
        for key, widget in (('arxml_only', self.arxml_only), ('skip_var_renames', self.skip_renames),
                            ('check_consistency', self.check_consistency), ('exit_zero', self.exit_zero)):
            widget.setChecked(self._config['compare'][key])
            compare_layout.addWidget(widget)
        self.rules = QPlainTextEdit(json.dumps(self._config['compare']['custom_rules'], indent=2))
        compare_layout.addWidget(QLabel(tr('Custom noise rules (JSON)')))
        import_rules = QPushButton(tr('Import Rules…'))
        import_rules.clicked.connect(self._import_rules)
        compare_layout.addWidget(import_rules)
        compare_layout.addWidget(self.rules)
        self.tabs.addTab(compare_tab, tr('Compare'))

        report_tab = QWidget()
        report_layout = QFormLayout(report_tab)
        self.report_theme = QComboBox()
        for value in theme.THEMES:
            self.report_theme.addItem(tr(value.title()), value)
        self.report_theme.setCurrentIndex(self.report_theme.findData(self._config['report']['theme']))
        self.report_enabled = QCheckBox(tr('Enable HTML report'))
        self.report_enabled.setChecked(self._config['report']['enabled'])
        self.max_lines = QLineEdit(str(self._config['report']['max_diff_lines']))
        report_layout.addRow(tr('Theme'), self.report_theme)
        report_layout.addRow(self.report_enabled)
        report_layout.addRow(tr('Max diff lines'), self.max_lines)
        self.tabs.addTab(report_tab, tr('Report'))
        actions = QHBoxLayout()
        for label, handler in (('Import Config…', self._import_config),
                               ('Export Config…', self._export_config),
                               ('Restore Defaults', self._restore_defaults)):
            button = QPushButton(tr(label))
            button.clicked.connect(handler)
            actions.addWidget(button)
        layout.addLayout(actions)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText(tr('Save'))
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr('Cancel'))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def preferences(self):
        display = self._config['display']
        return Preferences(self.language.currentData(), self.theme.currentData(),
                           display['comment'], display['unimportant'],
                           self.hide_identical.isChecked())

    def policy_path(self):
        path = self.policy.text().strip()
        return abspath(path) if path else ''

    def _pick_policy(self):
        tr = self._text
        path, _ = QFileDialog.getOpenFileName(
            self, tr('Code Check policy'), self.policy.text().strip(),
            tr('Policy files (*.yaml *.yml *.json);;All files (*)'))
        if path:
            try:
                loaded = load_checker_config(path)
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.warning(self, tr('Code Check policy'), str(exc))
                return
            self.policy_editor.set_policy(loaded)
            self.policy.setText(path)

    def config(self):
        value = deepcopy(self._config)
        value['appearance'].update(language=self.language.currentData(), theme=self.theme.currentData())
        value['display']['hide_identical'] = self.hide_identical.isChecked()
        value['compare'].update(exclude=[x.strip() for x in self.compare_exclude.toPlainText().splitlines() if x.strip()],
                                arxml_only=self.arxml_only.isChecked(), skip_var_renames=self.skip_renames.isChecked(),
                                check_consistency=self.check_consistency.isChecked(), exit_zero=self.exit_zero.isChecked(),
                                custom_rules=json.loads(self.rules.toPlainText()))
        value['code_check']['policy'] = self.policy_editor.policy()
        value['report'].update(theme=self.report_theme.currentData(), enabled=self.report_enabled.isChecked(),
                               max_diff_lines=int(self.max_lines.text()))
        return app_config.validate(value)

    def _load_fields(self, value):
        self._config = value
        self.language.setCurrentIndex(self.language.findData(value['appearance']['language']))
        self.theme.setCurrentIndex(self.theme.findData(value['appearance']['theme']))
        self.hide_identical.setChecked(value['display']['hide_identical'])
        self.compare_exclude.setPlainText('\n'.join(value['compare']['exclude']))
        for key, widget in (('arxml_only', self.arxml_only), ('skip_var_renames', self.skip_renames),
                            ('check_consistency', self.check_consistency), ('exit_zero', self.exit_zero)):
            widget.setChecked(value['compare'][key])
        self.rules.setPlainText(json.dumps(value['compare']['custom_rules'], indent=2))
        self.policy.clear()
        self.policy_editor.set_policy(value['code_check']['policy'])
        self.report_theme.setCurrentIndex(self.report_theme.findData(value['report']['theme']))
        self.report_enabled.setChecked(value['report']['enabled'])
        self.max_lines.setText(str(value['report']['max_diff_lines']))

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, self._text('Import Config…'), '', 'YAML (*.yaml *.yml)')
        if path:
            try:
                self._load_fields(app_config.load(path))
                self._replaced_config = True
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.warning(self, self._text('Settings'), str(exc))

    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(self, self._text('Export Config…'), '', 'YAML (*.yaml *.yml)')
        if path:
            try:
                store = getattr(self.parent(), '_settings', None)
                if (isinstance(store, YamlSettings) and store.recovering
                        and Path(path).resolve() == store.path.resolve()):
                    raise ValueError(self._text(_RECOVERY_REQUIRED))
                app_config.save(path, self.config())
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.warning(self, self._text('Settings'), str(exc))

    def _restore_defaults(self):
        self._load_fields(app_config.defaults())
        self._replaced_config = True

    def _import_rules(self):
        path, _ = QFileDialog.getOpenFileName(self, self._text('Import Rules…'), '', 'JSON (*.json)')
        if path:
            try:
                rules = read_items(path)
                candidate = app_config.defaults()
                candidate['compare']['custom_rules'] = rules
                app_config.validate(candidate)
                self.rules.setPlainText(json.dumps(rules, indent=2, ensure_ascii=False))
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.warning(self, self._text('Settings'), str(exc))
