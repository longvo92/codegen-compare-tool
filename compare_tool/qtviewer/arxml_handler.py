"""Qt workspace for previewing and applying validated AUTOSAR additions."""

from importlib import util
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..messages import Message
from .worker import TaskWorker


def path_field(parent, texts, title, *, schema=False):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    field = QLineEdit()
    field.setClearButtonEnabled(True)
    texts.bind(field.setPlaceholderText, title)
    browse = texts.widget(QPushButton, "Browse…")

    def choose():
        if schema:
            path, _ = QFileDialog.getOpenFileName(parent, texts(title), field.text(),
                                                 "XSD (*.xsd)")
        else:
            path = QFileDialog.getExistingDirectory(parent, texts(title), field.text())
        if path:
            field.setText(path)

    browse.clicked.connect(choose)
    layout.addWidget(field, 1)
    layout.addWidget(browse)
    return row, field


class ArxmlHandlerPage(QWidget):
    activity_changed = Signal()
    master_written = Signal(object, object)

    def __init__(self, texts, may_write, parent=None, *, protected_source=lambda _path: False):
        super().__init__(parent)
        self.tr_text = texts
        self.may_write = may_write
        self.protected_source = protected_source
        self.worker = None
        self.writing = False
        self.plan = None
        self.report_target = None
        self.undo = None
        self.repair = None
        self.undo_repair = None
        self.related = ()
        self.report_error = ""
        self.available = util.find_spec("lxml") is not None
        layout = QVBoxLayout(self)
        self.inputs = QWidget()
        form = QFormLayout(self.inputs)
        fields = []
        for title in ("Master folder to update", "Source ARXML folder", "Optional AUTOSAR XSD"):
            row, field = path_field(self, texts, title, schema=title.endswith("XSD"))
            label = texts.widget(QLabel, title)
            label.setBuddy(field)
            form.addRow(label, row)
            fields.append(field)
        self.master, self.source, self.xsd = fields
        self.master.textChanged.connect(self.invalidate)
        self.source.textChanged.connect(self.invalidate)
        layout.addWidget(self.inputs)

        buttons = QHBoxLayout()
        self.preview = texts.widget(QPushButton, "Preview Changes")
        self.apply = texts.widget(QPushButton, "Update Master")
        self.revert = texts.widget(QPushButton, "Undo Last Update")
        self.export = texts.widget(QPushButton, "Save Report")
        for button, callback in ((self.preview, self._preview), (self.apply, self._apply),
                                 (self.revert, self._revert), (self.export, self._export)):
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        layout.addWidget(texts.widget(QLabel, "Undo data is kept for this session only."))
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        texts.bind_labels(self.table.setHeaderLabels, ["Result", "Category", "AUTOSAR path", "Target file"])
        for column, width in enumerate((140, 160, 400, 260)):
            self.table.setColumnWidth(column, width)
        self.table.currentItemChanged.connect(self._details)
        layout.addWidget(self.table, 2)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        layout.addWidget(self.detail, 1)
        self.invalidate()

    @property
    def recovery_required(self):
        return self.undo is not None and self.undo.state == "recovery_required"

    def _show(self, message):
        self.message = message
        self.status.setText(self.tr_text(message))

    def retranslate(self):
        self._show(self.message)
        self._details(self.table.currentItem())

    def refresh_buttons(self):
        idle = self.worker is None
        master = self.master.text().strip()
        can_edit = idle and not self.recovery_required
        self.inputs.setEnabled(can_edit)
        self.preview.setEnabled(can_edit and self.available and bool(master and self.source.text().strip())
                                and not self.protected_source(master))
        self.apply.setEnabled(can_edit and self.may_write() and not self.protected_source(master) and bool(
            self.plan and self.plan.valid and self.plan.operations))
        try:
            same_master = bool(master and self.undo and self.undo.master_folder == Path(master).resolve())
        except (OSError, RuntimeError, ValueError):
            same_master = False
        self.revert.setEnabled(idle and self.may_write() and same_master and self.undo.can_revert)
        self.export.setEnabled(idle and self.report_target is not None)

    def invalidate(self):
        self.plan = self.report_target = self.repair = None
        self.report_error = ""
        self.related = ()
        self.table.clear()
        self.detail.clear()
        if self.protected_source(self.master.text().strip()):
            self._show("Select a working Master folder outside temporary comparison sources.")
        else:
            self._show("Select folders and preview changes." if self.available else
                       "ARXML repair requires lxml. Install codegen-compare-tool[arxml].")
        self.refresh_buttons()

    def load_repair(self, plan, related, verify, context):
        if self.worker or self.recovery_required:
            return False
        self.master.setText(str(plan.master.folder))
        self.source.setText(str(plan.source.folder))
        self.plan = self.report_target = plan
        self.report_error = ""
        self.related = related
        self.repair = (verify, context)
        self._display_plan()
        self.refresh_buttons()
        return True

    def _preview(self):
        master, source = self.master.text().strip(), self.source.text().strip()
        self.invalidate()

        def run():
            from ..arxml_handler import scan
            return scan(master, source)

        self._start("preview", run)

    def _apply(self):
        if not self.apply.isEnabled() or not self.may_write():
            return
        plan, xsd, repair = self.plan, self.xsd.text().strip() or None, self.repair

        def run():
            from ..arxml_handler import apply_patch
            if repair:
                repair[0](xsd)
            return apply_patch(plan, xsd)

        self._start("apply", run)

    def _revert(self):
        if not self.revert.isEnabled() or not self.may_write():
            return
        result = self.undo

        def run():
            from ..arxml_handler import revert_patch
            return revert_patch(result)

        self._start("undo", run)

    def _export(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr_text("Save Report"))
        if not folder:
            return
        target, error = self.report_target, self.report_error

        def run():
            from ..arxml_handler import save_report
            return save_report(target, folder, "failed" if error else "scanned", error)

        self._start("export", run)

    def _start(self, action, task):
        if self.worker is not None:
            return
        self.writing = action in ("apply", "undo")
        self.worker = TaskWorker(task, self)
        self.worker.finished.connect(self._finished)
        self.action = action
        self._show("Working…")
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
            self._show(Message("ARXML operation failed: {}", error))
            if self.action in ("apply", "undo"):
                self.report_error = str(error)
                transaction = getattr(error, "result", None)
                if transaction is not None:
                    self.report_target = transaction
                    if transaction.state == "recovery_required":
                        self.undo = transaction
                        if self.action == "apply":
                            self.undo_repair = self.repair
                        change = (transaction.master_folder, None)
                self.plan = None
        elif self.action == "preview":
            self.report_error = ""
            self.plan = self.report_target = result
            self._display_plan()
        elif self.action == "export":
            self._show(Message("Reports saved to {}.", result))
        else:
            self.report_error = ""
            self.report_target = result
            if self.action == "apply":
                self.undo = result
                self.undo_repair = self.repair
                self._show(Message("Updated {} Master file(s). {}",
                                   len(result.changed_files),
                                   Message("XSD validation passed.") if result.report["xsd_validated"]
                                   else Message("XSD validation was not run.")))
            else:
                self._show(Message("Restored {} Master file(s).", len(result.changed_files)))
            change = (result.master_folder, self.undo_repair[1] if self.undo_repair else None)
            self.plan = self.repair = None
            self.table.clear()
            self.detail.setPlainText("\n".join(map(str, result.changed_files)))
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
            if row.Action == "EXISTS":
                continue
            related = rows.get(id(row)) in self.related
            item = QTreeWidgetItem([row.Action + (" *" if related else ""),
                                    row.Category, row.ObjectPath, row.TargetFile])
            detail = [row.Reason, "Source: " + row.SourceFile, "Target: " + row.TargetFile]
            detail.extend(row.Dependencies)
            detail.extend("{} → {} ({})".format(u.OldUUID, u.NewUUID, u.Reason)
                          for u in self.plan.uuid_changes if
                          (u.ObjectPath, u.TargetFile) == (row.ObjectPath, row.TargetFile))
            item.setData(0, Qt.UserRole, "\n".join(detail))
            self.table.addTopLevelItem(item)
            if related and highlighted is None:
                highlighted = item
        for category, messages in (("ERROR", self.plan.errors), ("WARNING", self.plan.warnings)):
            for message in messages:
                item = QTreeWidgetItem([category, "", message])
                item.setData(0, Qt.UserRole, message)
                self.table.addTopLevelItem(item)
        self._show(Message("{} ADD · {} EXISTS · {} CONFLICT · {} UNSUPPORTED · {} error(s) · {} warning(s)",
                           *(self.plan.summary[key] for key in ("ADD", "EXISTS", "CONFLICT",
                                                                "UNSUPPORTED", "Errors")),
                           len(self.plan.warnings)))
        item = highlighted or self.table.topLevelItem(0)
        if item is not None:
            self.table.setCurrentItem(item)

    def _details(self, item, _previous=None):
        self.detail.setPlainText(item.data(0, Qt.UserRole) if item else "")
