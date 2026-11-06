"""Preferences for the viewer, and the single dialog that edits them."""

from typing import NamedTuple

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QLabel, QVBoxLayout)

from .. import APP_NAME, theme
from .icons import app_icon


class Preferences(NamedTuple):
    language: str = 'en'
    theme: str = theme.LIGHT
    comment: bool = True
    unimportant: bool = True
    hide_identical: bool = False


def preference_store():
    return QSettings('CodeGenInspector', APP_NAME)


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
    for key, value in prefs._asdict().items():
        store.setValue(key, value)
    store.sync()
    return store.status() == QSettings.Status.NoError


class SettingsDialog(QDialog):
    def __init__(self, parent, prefs, texts):
        super().__init__(parent)
        tr = texts
        self.setObjectName('viewerSettings')
        self.setWindowTitle(tr('Settings'))
        self.setWindowIcon(app_icon())
        layout = QVBoxLayout(self)

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
        layout.addWidget(appearance)

        display = QGroupBox(tr('Compare display'))
        options = QVBoxLayout(display)
        self.comment = QCheckBox(tr('Show Comment differences'))
        self.comment.setToolTip(tr('Mute Comment differences and skip them in F7/F8 when unchecked.'))
        self.unimportant = QCheckBox(tr('Show Unimportant differences'))
        self.unimportant.setToolTip(tr('Mute Unimportant differences and skip them in F7/F8 when unchecked.'))
        self.hide_identical = QCheckBox(tr('Hide identical'))
        self.hide_identical.setToolTip(tr('Hide only Identical files in the tree.'))
        for check, value in ((self.comment, prefs.comment), (self.unimportant, prefs.unimportant),
                             (self.hide_identical, prefs.hide_identical)):
            check.setChecked(value)
            options.addWidget(check)
        layout.addWidget(display)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText(tr('Save'))
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr('Cancel'))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def preferences(self):
        return Preferences(self.language.currentData(), self.theme.currentData(),
                           self.comment.isChecked(), self.unimportant.isChecked(),
                           self.hide_identical.isChecked())
