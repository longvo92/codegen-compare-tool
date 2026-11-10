"""Folder and ZIP source picker."""

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

from .. import theme, zipsource
from .icons import app_icon
from .i18n import Texts

def _err_qss():
    """The error strip, in theme roles -- resolved when the dialog is built, so
    it reads on both the light and the dark chrome. A hard-coded near-white on
    dark-red was invisible-adjacent on the light theme."""
    return ('color:{}; background:{}; border:1px solid {}; padding:5px 8px; '
            'border-radius:3px;'.format(theme.c('err-fg'), theme.c('err-bg'),
                                        theme.c('err-border')))


def _muted_qss(role='fg-dim', extra=''):
    """A muted label colour from a theme role. The dialogs used a fixed light
    grey (#9aa1ad / #8a8f98) that all but vanished on the light theme's white;
    a role flips with the chrome and stays legible on both."""
    return 'color:{};{}'.format(theme.c(role), extra)


class _PathRow(QHBoxLayout):
    """Label, the path itself, a Browse button, and (optionally) a Zip button
    -- so a side can be a folder or a ``.zip`` artifact."""

    def __init__(self, label, path, on_browse, on_zip=None, *, texts=None):
        super().__init__()
        self._text = Texts() if texts is None else texts
        tag = QLabel(self._text(label))
        tag.setMinimumWidth(64)  # fits 'BASELINE', the longest row label
        tag.setStyleSheet(_muted_qss('fg-dim'))
        self.edit = QLineEdit(str(path) if path else '')
        self.edit.setPlaceholderText(self._text('Choose a folder or a .zip…'))
        self.browse_button = QPushButton(self._text('Browse…'))
        self.browse_button.clicked.connect(on_browse)
        self.addWidget(tag)
        self.addWidget(self.edit, 1)
        self.addWidget(self.browse_button)
        if on_zip is not None:
            zbtn = QPushButton(self._text('Zip…'))
            zbtn.clicked.connect(on_zip)
            self.addWidget(zbtn)

    def text(self):
        return self.edit.text().strip()

    def set_text(self, value):
        self.edit.setText(str(value))


class FolderPicker(QDialog):
    """BASELINE and CURRENT side by side, both prefilled and both editable.

    Two native folder dialogs in a row forced the reviewer to re-pick the side
    they were happy with just to change the other one. Here each side is one
    click, and typing or pasting a path works too.
    """

    def __init__(self, parent, old=None, new=None):
        super().__init__(parent)
        self._text = getattr(parent, "_text", Texts())
        self.chosen = None
        self.setWindowTitle(self._text('Compare two folders'))
        self.setWindowIcon(app_icon())
        self.resize(680, 200)

        self.old_row = _PathRow('BASELINE', old,
                                lambda: self._browse(self.old_row, 'BASELINE'),
                                lambda: self._browse_zip(self.old_row, 'BASELINE'), texts=self._text)
        self.new_row = _PathRow('CURRENT', new,
                                lambda: self._browse(self.new_row, 'CURRENT'),
                                lambda: self._browse_zip(self.new_row, 'CURRENT'), texts=self._text)
        for row in (self.old_row, self.new_row):
            row.edit.textChanged.connect(self._sync_ok)

        hint = QLabel(self._text('BASELINE is the previous generation, CURRENT is the one being reviewed. Either can be a folder or a .zip.'))
        hint.setStyleSheet(_muted_qss('fg-muted', ' font-size:11px;'))

        self.error = QLabel('')
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        self.error.setStyleSheet(_err_qss())

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(self._text('Compare'))
        self.buttons.button(QDialogButtonBox.Cancel).setText(self._text('Cancel'))
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.addLayout(self.old_row)
        lay.addLayout(self.new_row)
        lay.addWidget(hint)
        lay.addStretch(1)
        lay.addWidget(self.error)
        lay.addWidget(self.buttons)
        self._sync_ok()

    def _start_dir(self, row):
        """Where a browse dialog for ``row`` should open.

        BASELINE and CURRENT are almost always siblings -- ``old/`` and ``new/``
        under one parent. So a side that is still empty opens in the *other*
        side's parent, where the folder to pick is sitting right next to it:
        set BASELINE to ``…/funcdemo/old`` and browsing CURRENT lands in
        ``…/funcdemo``. Once a side has its own path, re-browsing stays there.
        """
        other = self.new_row if row is self.old_row else self.old_row
        mine = row.text()
        if mine:
            p = Path(mine)
            return str(p if p.is_dir() else p.parent)
        theirs = other.text()
        return str(Path(theirs).parent) if theirs else ''

    def _browse(self, row, label):
        picked = QFileDialog.getExistingDirectory(
            self, self._text('Select the {} folder', label), self._start_dir(row))
        if picked:
            row.set_text(picked)

    def _browse_zip(self, row, label):
        picked, _ = QFileDialog.getOpenFileName(
            self, self._text('Select the {} zip', label), self._start_dir(row),
            self._text('Zip artifact (*.zip)'))
        if picked:
            row.set_text(picked)

    def _sync_ok(self):
        ok = bool(self.old_row.text()) and bool(self.new_row.text())
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(ok)
        self.error.setVisible(False)

    def _accept(self):
        old, new = self.old_row.text(), self.new_row.text()
        for path, label in ((old, 'BASELINE'), (new, 'CURRENT')):
            # a side is valid as a folder OR a .zip; anything else is caught
            # here, before the scan, so a typo is not reported as a compare
            # error later
            if not (Path(path).is_dir() or zipsource.is_zip(path)):
                self.error.setText(
                    self._text('{} is not a folder or a .zip: {}', label, path))
                self.error.setVisible(True)
                return
        self.chosen = (old, new)
        self.accept()


def pick_folders(parent, old=None, new=None):
    """Run the folder dialog; return ``(old, new)`` or None."""
    dlg = FolderPicker(parent, old, new)
    return dlg.chosen if dlg.exec() else None
