"""The two dialogs that start a compare: pick two folders, or pick a commit.

Both follow the same rule, learned the hard way: **a dialog shows everything it
is about to use, and lets you change any of it.** The first version of the git
flow silently reused whichever folder happened to be loaded, which meant that
once you had compared one folder against its history there was no way to point
it at a different one short of restarting the app. Nothing here is remembered
behind the reviewer's back.

The dialogs stay dumb: they render what they are handed and call back for the
work. Deciding what a commit is and getting its files onto disk stays in
:mod:`compare_tool.gitsource`, so the CLI could use it too.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from .. import zipsource
from .icons import app_icon

_COMMIT_ROLE = Qt.UserRole

_ERR_QSS = ('color:#ffd6d6; background:#4a1d1d; padding:5px 8px; '
            'border-radius:3px;')


def _esc(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


class _PathRow(QHBoxLayout):
    """Label, the path itself, a Browse button, and (optionally) a Zip button
    -- so a side can be a folder or a ``.zip`` artifact."""

    def __init__(self, label, path, on_browse, on_zip=None):
        super().__init__()
        tag = QLabel(label)
        tag.setMinimumWidth(64)  # fits 'BASELINE', the longest row label
        tag.setStyleSheet('color:#9aa1ad;')
        self.edit = QLineEdit(str(path) if path else '')
        self.edit.setPlaceholderText('Choose a folder or a .zip…')
        btn = QPushButton('Browse…')
        btn.clicked.connect(on_browse)
        self.addWidget(tag)
        self.addWidget(self.edit, 1)
        self.addWidget(btn)
        if on_zip is not None:
            zbtn = QPushButton('Zip…')
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
        self.chosen = None
        self.setWindowTitle('Compare two folders')
        self.setWindowIcon(app_icon())
        self.resize(680, 200)

        self.old_row = _PathRow('BASELINE', old,
                                lambda: self._browse(self.old_row, 'BASELINE'),
                                lambda: self._browse_zip(self.old_row, 'BASELINE'))
        self.new_row = _PathRow('CURRENT', new,
                                lambda: self._browse(self.new_row, 'CURRENT'),
                                lambda: self._browse_zip(self.new_row, 'CURRENT'))
        for row in (self.old_row, self.new_row):
            row.edit.textChanged.connect(self._sync_ok)

        hint = QLabel('BASELINE is the previous generation, CURRENT is the one '
                      'being reviewed. Either can be a folder or a .zip.')
        hint.setStyleSheet('color:#8a8f98; font-size:11px;')

        self.error = QLabel('')
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        self.error.setStyleSheet(_ERR_QSS)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText('Compare')
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

    def _browse(self, row, label):
        start = row.text() or self.old_row.text() or self.new_row.text() or ''
        picked = QFileDialog.getExistingDirectory(
            self, 'Select the {} folder'.format(label), start)
        if picked:
            row.set_text(picked)

    def _browse_zip(self, row, label):
        start = row.text() or self.old_row.text() or self.new_row.text() or ''
        picked, _ = QFileDialog.getOpenFileName(
            self, 'Select the {} zip'.format(label),
            str(Path(start).parent) if start else '', 'Zip artifact (*.zip)')
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
                    '{} is not a folder or a .zip: {}'.format(label, path))
                self.error.setVisible(True)
                return
        self.chosen = (old, new)
        self.accept()


class CommitPicker(QDialog):
    """Which folder, and which of its commits, becomes the BASELINE side.

    The folder lives in this dialog too. Commits are listed for that folder
    only -- that is what keeps the list short enough to read -- so changing the
    folder has to reload the list, and doing it anywhere else would mean
    closing and reopening the window to point somewhere new.

    Anything outside the listed commits (a branch, a tag, `HEAD~20`) goes
    through the revision box, so the filtered list is never a cage.
    """

    def __init__(self, parent, folder, load, resolve):
        super().__init__(parent)
        self._load = load          # folder -> (root, sub, [Commit])
        self._resolve = resolve    # (root, rev) -> Commit
        self.folder = str(folder) if folder else ''
        self.root = None
        self.sub = ''
        self.chosen = None

        self.setWindowTitle('Compare with a commit')
        self.setWindowIcon(app_icon())
        self.resize(880, 560)

        self.folder_row = _PathRow('Folder', self.folder, self._change_folder)
        self.folder_row.edit.setReadOnly(True)  # Browse is the only way in
        self.where = QLabel('')
        # lines up under the path text, not the tag: the tag column is now
        # sized for 'BASELINE' in the other dialog, wider than 'Folder' here
        self.where.setStyleSheet('color:#9aa1ad; font-size:11px; padding-left:68px;')

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('Filter commits…')
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._refilter)

        self.list = QTreeWidget()
        self.list.setHeaderLabels(['Commit', 'Date', 'Author', 'Subject'])
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setAlternatingRowColors(True)
        self.list.itemSelectionChanged.connect(self._sync_ok)
        self.list.itemDoubleClicked.connect(lambda *_: self._accept_selected())

        self.rev_edit = QLineEdit()
        self.rev_edit.setPlaceholderText('…or a sha, branch, tag, HEAD~3')
        self.rev_edit.returnPressed.connect(self._use_revision)
        rev_btn = QPushButton('Use revision')
        rev_btn.clicked.connect(self._use_revision)
        rev = QHBoxLayout()
        rev.addWidget(self.rev_edit, 1)
        rev.addWidget(rev_btn)

        self.error = QLabel('')
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        self.error.setStyleSheet(_ERR_QSS)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText('Compare')
        self.buttons.accepted.connect(self._accept_selected)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.addLayout(self.folder_row)
        lay.addWidget(self.where)
        lay.addWidget(self.filter_edit)
        lay.addWidget(self.list, 1)
        lay.addLayout(rev)
        lay.addWidget(self.error)
        lay.addWidget(self.buttons)

        if self.folder:
            self._reload()
        else:
            # nothing to list yet: ask for the folder as the window comes up,
            # rather than showing an empty table and waiting to be understood
            QTimer.singleShot(0, self._change_folder)
        self._sync_ok()

    # --- folder ---

    def _change_folder(self):
        picked = QFileDialog.getExistingDirectory(
            self, 'Select the folder to review (inside a git checkout)',
            self.folder or '')
        if not picked:
            return
        self.folder = picked
        self.folder_row.set_text(picked)
        self._reload()

    def _reload(self):
        """Re-list the commits for the current folder."""
        self.list.clear()
        self.root, self.sub = None, ''
        self.where.setText('')
        try:
            root, sub, commits = self._load(self.folder)
        except Exception as e:
            self._show_error('{}'.format(e))
            self._sync_ok()
            return
        self.error.setVisible(False)
        self.root, self.sub = root, sub
        self.where.setText('{}  ·  {}'.format(
            Path(str(root)).name, sub or 'whole repository'))
        for c in commits:
            item = QTreeWidgetItem([c.short, c.when, c.author, c.subject])
            item.setData(0, _COMMIT_ROLE, c)
            self.list.addTopLevelItem(item)
        for col in range(3):
            self.list.resizeColumnToContents(col)
        if commits:
            self.list.setCurrentItem(self.list.topLevelItem(0))
        else:
            self._show_error('No commit in this repository touches {}. The '
                             'folder may be untracked or ignored.'
                             .format(sub or 'the repository'))
        self._refilter(self.filter_edit.text())
        self._sync_ok()

    # --- selection ---

    def _selected(self):
        items = self.list.selectedItems()
        if not items or items[0].isHidden():
            return None
        return items[0].data(0, _COMMIT_ROLE)

    def _sync_ok(self):
        ready = self.root is not None and self._selected() is not None
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(ready)

    def _accept_selected(self):
        c = self._selected()
        if c is None or self.root is None:
            return
        self.chosen = (self.folder, self.root, self.sub, c)
        self.accept()

    def _use_revision(self):
        """Resolve what was typed. A bad revision is shown in the dialog, not
        as a second popup on top of it."""
        text = self.rev_edit.text().strip()
        if not text or self.root is None:
            return
        try:
            commit = self._resolve(self.root, text)
        except Exception as e:
            self._show_error('{}'.format(e))
            return
        self.chosen = (self.folder, self.root, self.sub, commit)
        self.accept()

    def _show_error(self, msg):
        self.error.setText(_esc(msg))
        self.error.setVisible(True)

    # --- filtering: hide rows, never reorder them ---

    def _refilter(self, text):
        needle = text.strip().lower()
        for i in range(self.list.topLevelItemCount()):
            item = self.list.topLevelItem(i)
            hay = ' '.join(item.text(c) for c in range(4)).lower()
            item.setHidden(bool(needle) and needle not in hay)
        self._sync_ok()


def pick_folders(parent, old=None, new=None):
    """Run the folder dialog; return ``(old, new)`` or None."""
    dlg = FolderPicker(parent, old, new)
    return dlg.chosen if dlg.exec() else None


def pick_commit(parent, folder, load, resolve):
    """Run the commit dialog; return ``(folder, root, sub, commit)`` or None."""
    dlg = CommitPicker(parent, folder, load, resolve)
    return dlg.chosen if dlg.exec() else None
