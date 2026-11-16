"""Review notes and sign-off for the change under the cursor.

The panel edits a :class:`compare_tool.review.ReviewStore`: one note and one
Reviewed flag per reviewable unit (real and moved hunks, or one whole-file unit
for added, deleted and binary files). Units are content-addressed, so a change
regenerated differently comes back unreviewed. The store is the same object
the HTML export renders, so the CLI ``--review`` file and the viewer agree.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QPlainTextEdit, QToolButton, QVBoxLayout)

from .. import review, theme


class _NoteEdit(QPlainTextEdit):
    """Note box that reports when focus leaves it, so a typed note is saved
    before the reviewer moves on."""

    left = Signal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.left.emit()


class ReviewPanel(QFrame):
    """Note box, Reviewed tick and whole-file sign-off for one diff pane."""

    saved = Signal(str)   # status message after a write (or a failed one)

    def __init__(self, texts, parent=None):
        """The owner pushes the change under the cursor with :meth:`show_unit`.
        The panel holds no reference to the diff pane: a diff -> panel signal
        plus a panel -> diff attribute would form a reference cycle that only
        the cyclic GC frees, possibly on a worker thread, where deleting Qt
        widgets crashes."""
        super().__init__(parent)
        self.setObjectName('reviewbar')
        self._text = texts
        self.store = review.ReviewStore()
        self._unit = None  # (rel, key, label) the note box is editing
        self._current = None  # (rel, key, label) under the cursor, or None
        self._file_units = []  # every reviewable unit of the file on screen

        self.note_edit = _NoteEdit()
        self.note_edit.setFixedHeight(58)
        self.note_edit.setTabChangesFocus(True)
        self.note_edit.left.connect(self.commit)
        # debounce as well as focus-out: a note typed and never left behind
        # (window closed, app killed) still reaches the file
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(800)
        self._timer.timeout.connect(self.commit)
        self.note_edit.textChanged.connect(self._timer.start)

        self.cb_reviewed = QCheckBox()
        texts.bind(self.cb_reviewed.setText, 'Reviewed')
        texts.bind(self.cb_reviewed.setToolTip,
                   'Sign this change off (Ctrl+R). Exported reports can hide signed-off changes.')
        self.cb_reviewed.toggled.connect(self.commit)
        self.btn_file = QToolButton()
        self.btn_file.setCursor(Qt.PointingHandCursor)
        self.btn_file.clicked.connect(self.toggle_file)
        self.where = QLabel('')
        self.file_label = QLabel('')

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(2)
        for widget in (self.cb_reviewed, self.btn_file, self.where, self.file_label):
            side.addWidget(widget)
        side.addStretch(1)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(10)
        row.addWidget(self.note_edit, 1)
        row.addLayout(side)
        self.refresh()

    # --- store lifecycle ---

    def open(self, path):
        """Load the review file for a new comparison. An unreadable file
        disables editing and is never written over (see ReviewStore.load)."""
        self.commit()
        self._unit = None
        self.store = review.ReviewStore.load(path) if path else review.ReviewStore()
        self.refresh()

    def reset(self):
        self.commit()
        self._unit = None
        self.store = review.ReviewStore()
        self.refresh()

    # --- edits ---

    def show_unit(self, unit, file_units):
        """The cursor moved. Save the previous unit's note, then load the
        current one: this one seam covers F7/F8, clicks, file changes and
        rescans. ``unit`` is ``(rel, key, label)`` or None; ``file_units``
        are the file's reviewable :class:`compare_tool.review.Unit` items."""
        self.commit()
        self._current = unit
        self._file_units = list(file_units)
        self.refresh()

    def commit(self):
        """Write the box back to the store and to disk when it changed."""
        self._timer.stop()
        unit = self._unit
        if unit is None or self.store.error or self.store.path is None:
            return
        rel, key, label = unit
        note = self.note_edit.toPlainText()
        reviewed = self.cb_reviewed.isChecked()
        if (note.strip() == self.store.note(rel, key)
                and reviewed == self.store.is_reviewed(rel, key)):
            return
        self.store.set(rel, key, note, reviewed, label)
        self._save()
        self._sync_file_button()  # the last tick can complete the file

    def toggle_reviewed(self):
        if self.cb_reviewed.isEnabled():
            self.cb_reviewed.toggle()  # toggled commits

    def toggle_file(self):
        self.commit()
        rel, units, done = self._file_state()
        if rel is None:
            return
        changed = review.mark_file(self.store, rel, units, not done)
        if changed:
            self._save()
        self.refresh()

    # --- display ---

    def _file_state(self):
        """``(rel, units, all_reviewed)``; ``rel`` is None when nothing on the
        file can be signed off (noise-only, not compared, or no usable store)."""
        unit = self._current
        units = self._file_units
        if unit is None or not units or self.store.error or self.store.path is None:
            return None, [], False
        rel = unit[0]
        return rel, units, all(self.store.is_reviewed(rel, u.key) for u in units)

    def refresh(self):
        tr = self._text
        unit = self._current
        self._unit = unit
        usable = self.store.path is not None and not self.store.error
        editable = unit is not None and usable
        if self.store.error:
            hint = tr('The review file could not be read; editing is off.')
        elif self.store.path is None:
            hint = tr('Run a comparison to review its changes.')
        elif unit is None:
            hint = tr('No change to review here.')
        else:
            hint = tr('Why this change? Purpose, decision, ticket…')
        self.note_edit.setPlaceholderText(hint)
        self.note_edit.setEnabled(editable)
        self.cb_reviewed.setEnabled(editable)
        self.note_edit.blockSignals(True)
        self.cb_reviewed.blockSignals(True)
        if unit and usable:
            rel, key, label = unit
            self.note_edit.setPlainText(self.store.note(rel, key))
            self.cb_reviewed.setChecked(self.store.is_reviewed(rel, key))
            self.where.setText(label)
        else:
            self.note_edit.setPlainText('')
            self.cb_reviewed.setChecked(False)
            self.where.setText('')
        self.note_edit.blockSignals(False)
        self.cb_reviewed.blockSignals(False)
        self._sync_file_button()
        self._show_file()

    def _sync_file_button(self):
        tr = self._text
        rel, units, done = self._file_state()
        self.btn_file.setEnabled(rel is not None)
        self.btn_file.setText(tr('Clear file') if done else tr('Whole file'))
        self.btn_file.setToolTip(
            tr('Nothing in this file can be signed off.') if rel is None else
            tr('Sign off or clear all {} change(s) in this file (Ctrl+Shift+R). Notes are kept.',
               len(units)))

    def _show_file(self):
        path = self.store.path
        muted = 'color:{}; font-size:11px;'.format(theme.c('fg-muted'))
        if path is None:
            self.file_label.setText('')
            self.file_label.setStyleSheet(muted)
            self.file_label.setToolTip('')
            return
        if self.store.error:
            self.file_label.setText('⚠ {}'.format(Path(path).name))
            self.file_label.setStyleSheet('color:{}; font-size:11px;'.format(theme.c('st-err')))
            self.file_label.setToolTip(self._text(
                '{}\n\n{}\n\nNothing is loaded from it or written over it. Fix or remove the file, then rescan.',
                path, self.store.error))
        else:
            self.file_label.setText(Path(path).name)
            self.file_label.setStyleSheet(muted)
            self.file_label.setToolTip(self._text('Notes and sign-offs are saved to\n{}', path))

    def _save(self):
        try:
            self.store.save()
        except Exception as e:  # keep the in-memory note; say it was not saved
            self.saved.emit(self._text('Review NOT saved to {}: {}: {}',
                                       self.store.path, type(e).__name__, e))
            return
        self.saved.emit(self._text('Review saved to {}', self.store.path))
