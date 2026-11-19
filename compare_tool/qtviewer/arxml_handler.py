"""ARXML Handler tool: Master/Source fields, filled from Code Check or typed, around the shared RepairPanel."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from ..fix_sources import detect_fix_sources
from ..messages import Message
from .repair_panel import RepairPanel
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
    """The manual patcher. It lives in its own window under Tools; Code Check
    repairs a finding with its own inline panel instead of handing over here."""

    title_key = 'ARXML Handler'

    def __init__(self, texts, may_write, parent=None, *, protected_source=lambda _path: False,
                 repair_settings=lambda: {"codegen_root": "", "xsd": ""}, check_inputs=lambda: None):
        super().__init__(parent)
        self.tr_text = texts
        self.repair_settings = repair_settings
        # () -> (root, check, exclude) of a usable Code Check result, or None
        self.check_inputs = check_inputs
        self.fill_worker = None
        self._sources = None   # FixSources whose staged copy the Source field may point at
        self._fill_message = ""
        layout = QVBoxLayout(self)
        self.inputs = QWidget()
        form = QFormLayout(self.inputs)
        fields = []
        for title in ("Master folder to update", "Source ARXML folder"):
            row, field = path_field(self, texts, title)
            label = texts.widget(QLabel, title)
            label.setBuddy(field)
            form.addRow(label, row)
            fields.append(field)
        self.master, self.source = fields
        # the same detection Code Check uses fills both fields; they stay editable
        fill_row = QHBoxLayout()
        self.fill = texts.widget(QPushButton, "Fill from Code Check")
        texts.bind(self.fill.setToolTip, "Find Master and the generated Source ARXML from the last Code Check.")
        self.fill.clicked.connect(self.fill_from_check)
        fill_row.addWidget(self.fill)
        fill_row.addStretch()
        form.addRow(fill_row)
        self.fill_note = QLabel()
        self.fill_note.setWordWrap(True)
        self.fill_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fill_note.setMinimumWidth(1)
        form.addRow(self.fill_note)
        layout.addWidget(self.inputs)
        self.panel = RepairPanel(texts, may_write, self.paths, self,
                                 protected_source=protected_source, manual=True)
        layout.addWidget(self.panel, 1)
        # the panel's widgets, under the names the page always had
        self.preview, self.apply = self.panel.preview, self.panel.apply
        self.revert, self.export = self.panel.revert, self.panel.export
        self.status, self.table, self.detail = self.panel.status, self.panel.table, self.panel.detail
        self.activity_changed = self.panel.activity_changed
        self.master_written = self.panel.master_written
        self.activity_changed.connect(self._refresh_inputs)
        self.master.textChanged.connect(self.invalidate)
        self.source.textChanged.connect(self.invalidate)
        self.invalidate()

    def paths(self):
        # the optional XSD comes from Settings > Code Check > ARXML repair
        return (self.master.text().strip(), self.source.text().strip(),
                self.repair_settings().get("xsd") or None)

    def fill_from_check(self, *_args):
        if self.fill_worker is not None or not self.panel.editable:
            return
        inputs = self.check_inputs()
        if inputs is None:
            self._show_fill([Message("Run Code Check on a working folder first.")])
            return
        root, check, exclude = inputs
        codegen = self.repair_settings().get("codegen_root", "")
        self.fill_worker = TaskWorker(
            lambda: detect_fix_sources(root, check, exclude, codegen_root=codegen), self)
        self.fill_worker.finished.connect(self._fill_finished)
        self._show_fill([Message("Looking for the generated ARXML…")])
        self.fill_worker.start()
        self._refresh_inputs()

    def _fill_finished(self):
        worker, self.fill_worker = self.fill_worker, None
        worker.deleteLater()
        sources = worker.result
        if worker.error is not None:
            self._show_fill([Message("Generated ARXML could not be located: {}", worker.error)])
        elif sources.problem is not None or sources.staged is None or sources.master is None:
            sources.close()
            self._show_fill(sources.problems() or [Message("No generated ARXML matches the code.")])
        else:
            # fill both fields first: each edit releases a copy nothing points at
            previous, self._sources = self._sources, None
            self.master.setText(str(sources.master))
            self.source.setText(str(sources.staged))
            self._sources = sources
            if previous is not None:
                previous.close()
            self._show_fill([])   # the filled fields say what was found
        self._refresh_inputs()

    def _show_fill(self, lines):
        self._fill_lines = list(lines)
        self.fill_note.setText("\n".join(self.tr_text(line) for line in self._fill_lines))

    def _release_sources(self, force=False):
        sources = self._sources
        if sources is None or sources.staged is None:
            return
        in_use = (self.source.text().strip() == str(sources.staged)
                  or self.panel.worker is not None or self.panel.plan is not None)
        if force or not in_use:
            sources.close()
            self._sources = None

    def release_sources(self):
        """The application is closing: drop the staged copy."""
        self._release_sources(force=True)

    def staged_folders(self):
        return [self._sources.staged] if self._sources is not None and self._sources.staged else []

    @property
    def worker(self):
        return self.panel.worker

    @property
    def writing(self):
        return self.panel.writing

    @property
    def recovery_required(self):
        return self.panel.recovery_required

    def retranslate(self):
        self.panel.retranslate()
        self._show_fill(getattr(self, "_fill_lines", []))

    def invalidate(self, *_args):
        self.panel.invalidate()
        self._release_sources()
        self._refresh_inputs()

    def refresh_buttons(self, *_args):
        self.panel.refresh_buttons()
        self._refresh_inputs()

    def _refresh_inputs(self):
        self.inputs.setEnabled(self.panel.editable and self.fill_worker is None)
