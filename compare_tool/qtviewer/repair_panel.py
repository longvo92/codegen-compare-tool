"""ARXML repair panel: preview, apply, undo and report one ARXML patch plan.

One engine, two hosts. Code Check embeds it under a FAIL finding to apply the
repair it has already verified; the ARXML Handler tool window embeds it behind
its own Master/Source/XSD fields for a manual patch. The host supplies the paths
and decides whether the manual **Preview Changes** scan is offered.

Writing is never silent: an apply re-runs the host's verification first, a
failed transaction keeps its undo data and blocks further edits until it is
reverted, and every result is shown in the table and status line.
"""

from importlib import util
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..messages import Message
from .worker import TaskWorker

NO_PATHS = ('', '', None)


class RepairPanel(QWidget):
    """``paths()`` returns ``(master, source, xsd_or_None)`` from the host's fields."""

    activity_changed = Signal()
    master_written = Signal(object, object)

    def __init__(self, texts, may_write, paths, parent=None, *,
                 protected_source=lambda _path: False, manual=True):
        super().__init__(parent)
        self.tr_text = texts
        self.may_write = may_write
        self.paths = paths
        self.protected_source = protected_source
        self.manual = manual
        self.worker = None
        self.writing = False
        self.action = None
        self.plan = None
        self.report_target = None
        self.undo = None
        self.repair = None
        self.undo_repair = None
        self.related = ()
        self.report_error = ''
        self.message = ''
        self.available = util.find_spec('lxml') is not None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        buttons = QHBoxLayout()
        self.preview = texts.widget(QPushButton, 'Preview Changes')
        self.apply = texts.widget(QPushButton, 'Update Master')
        self.revert = texts.widget(QPushButton, 'Undo Last Update')
        self.export = texts.widget(QPushButton, 'Save Report')
        for button, callback in ((self.preview, self._preview), (self.apply, self._apply),
                                 (self.revert, self._revert), (self.export, self._export)):
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.preview.setVisible(manual)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        layout.addWidget(texts.widget(QLabel, 'Undo data is kept for this session only.'))
        split = QSplitter(Qt.Vertical)
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        texts.bind_labels(self.table.setHeaderLabels, ['Result', 'Category', 'AUTOSAR path', 'Target file'])
        for column, width in enumerate((140, 160, 400, 260)):
            self.table.setColumnWidth(column, width)
        self.table.currentItemChanged.connect(self._details)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)

    # --- state the hosts read ---

    @property
    def recovery_required(self):
        return self.undo is not None and self.undo.state == 'recovery_required'

    @property
    def editable(self):
        """The host's path fields may change: nothing running, nothing to recover."""
        return self.worker is None and not self.recovery_required

    @property
    def has_plan(self):
        return self.plan is not None

    def _show(self, message):
        self.message = message
        self.status.setText(self.tr_text(message))

    def retranslate(self):
        self._show(self.message)
        self._details(self.table.currentItem())

    def refresh_buttons(self):
        master, source, _xsd = self.paths()
        idle = self.worker is None
        can_edit = idle and not self.recovery_required
        self.preview.setEnabled(can_edit and self.available and bool(master and source)
                                and not self.protected_source(master))
        self.apply.setEnabled(can_edit and self.may_write() and not self.protected_source(master) and bool(
            self.plan and self.plan.valid and self.plan.operations))
        try:
            same_master = bool(master and self.undo and self.undo.master_folder == Path(master).resolve())
        except (OSError, RuntimeError, ValueError):
            same_master = False
        self.revert.setEnabled(idle and self.may_write() and same_master and self.undo.can_revert)
        self.export.setEnabled(idle and self.report_target is not None)

    def invalidate(self, message=None):
        """Drop the plan; a changed input must never apply an old preview."""
        self.plan = self.report_target = self.repair = None
        self.report_error = ''
        self.related = ()
        self.table.clear()
        self.detail.clear()
        master = self.paths()[0]
        if message is not None:
            self._show(message)
        elif self.protected_source(master):
            self._show('Select a working Master folder outside temporary comparison sources.')
        elif not self.available:
            self._show('ARXML repair requires lxml. Install codegen-compare-tool[arxml].')
        else:
            self._show('Select folders and preview changes.')
        self.refresh_buttons()

    def load_repair(self, plan, related, verify, context):
        """Show a plan the host has already verified. ``verify(xsd)`` runs again
        right before writing; ``context`` travels with ``master_written``."""
        if self.worker or self.recovery_required:
            return False
        self.plan = self.report_target = plan
        self.report_error = ''
        self.related = related
        self.repair = (verify, context)
        self._display_plan()
        self.refresh_buttons()
        return True

    # --- operations, each on a worker ---

    def _preview(self):
        master, source, _xsd = self.paths()
        self.invalidate()

        def run():
            from ..arxml_handler import scan
            return scan(master, source)

        self._start('preview', run)

    def _apply(self):
        if not self.apply.isEnabled() or not self.may_write():
            return
        plan, xsd, repair = self.plan, self.paths()[2], self.repair

        def run():
            from ..arxml_handler import apply_patch
            if repair:
                repair[0](xsd)
            return apply_patch(plan, xsd)

        self._start('apply', run)

    def _revert(self):
        if not self.revert.isEnabled() or not self.may_write():
            return
        result = self.undo

        def run():
            from ..arxml_handler import revert_patch
            return revert_patch(result)

        self._start('undo', run)

    def _export(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr_text('Save Report'))
        if not folder:
            return
        target, error = self.report_target, self.report_error

        def run():
            from ..arxml_handler import save_report
            return save_report(target, folder, 'failed' if error else 'scanned', error)

        self._start('export', run)

    def _start(self, action, task):
        if self.worker is not None:
            return
        self.writing = action in ('apply', 'undo')
        self.worker = TaskWorker(task, self)
        self.worker.finished.connect(self._finished)
        self.action = action
        self._show('Working…')
        self.worker.start()
        self.activity_changed.emit()
        self.refresh_buttons()

    def _finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.writing = False
        result, error = worker.result, worker.error
        change = None
        if error:
            self._show(Message('ARXML operation failed: {}', error))
            if self.action in ('apply', 'undo'):
                self.report_error = str(error)
                transaction = getattr(error, 'result', None)
                if transaction is not None:
                    self.report_target = transaction
                    if transaction.state == 'recovery_required':
                        self.undo = transaction
                        if self.action == 'apply':
                            self.undo_repair = self.repair
                        change = (transaction.master_folder, None)
                self.plan = None
        elif self.action == 'preview':
            self.report_error = ''
            self.plan = self.report_target = result
            self._display_plan()
        elif self.action == 'export':
            self._show(Message('Reports saved to {}.', result))
        else:
            self.report_error = ''
            self.report_target = result
            if self.action == 'apply':
                self.undo = result
                self.undo_repair = self.repair
                self._show(Message('Updated {} Master file(s). {}',
                                   len(result.changed_files),
                                   Message('XSD validation passed.') if result.report['xsd_validated']
                                   else Message('XSD validation was not run.')))
            else:
                self._show(Message('Restored {} Master file(s).', len(result.changed_files)))
            change = (result.master_folder, self.undo_repair[1] if self.undo_repair else None)
            self.plan = self.repair = None
            self.table.clear()
            self.detail.setPlainText('\n'.join(map(str, result.changed_files)))
        self.activity_changed.emit()
        self.refresh_buttons()
        if change:
            self.master_written.emit(*change)

    def _display_plan(self):
        self.table.clear()
        self.detail.clear()
        rows = {id(op.record): i for i, op in enumerate(self.plan.operations)}
        highlighted = None
        for row in self.plan.records:
            if row.Action == 'EXISTS':
                continue
            related = rows.get(id(row)) in self.related
            item = QTreeWidgetItem([row.Action + (' *' if related else ''),
                                    row.Category, row.ObjectPath, row.TargetFile])
            detail = [row.Reason, 'Source: ' + row.SourceFile, 'Target: ' + row.TargetFile]
            detail.extend(row.Dependencies)
            detail.extend('{} → {} ({})'.format(u.OldUUID, u.NewUUID, u.Reason)
                          for u in self.plan.uuid_changes if
                          (u.ObjectPath, u.TargetFile) == (row.ObjectPath, row.TargetFile))
            item.setData(0, Qt.UserRole, '\n'.join(detail))
            self.table.addTopLevelItem(item)
            if related and highlighted is None:
                highlighted = item
        for category, messages in (('ERROR', self.plan.errors), ('WARNING', self.plan.warnings)):
            for message in messages:
                item = QTreeWidgetItem([category, '', message])
                item.setData(0, Qt.UserRole, message)
                self.table.addTopLevelItem(item)
        self._show(Message('{} ADD · {} EXISTS · {} CONFLICT · {} UNSUPPORTED · {} error(s) · {} warning(s)',
                           *(self.plan.summary[key] for key in ('ADD', 'EXISTS', 'CONFLICT',
                                                                'UNSUPPORTED', 'Errors')),
                           len(self.plan.warnings)))
        item = highlighted or self.table.topLevelItem(0)
        if item is not None:
            self.table.setCurrentItem(item)

    def _details(self, item, _previous=None):
        self.detail.setPlainText(item.data(0, Qt.UserRole) if item else '')
