"""ARXML Handler tool: manual Master/Source/XSD fields around the shared RepairPanel."""

from PySide6.QtWidgets import (QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from .repair_panel import RepairPanel


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

    def __init__(self, texts, may_write, parent=None, *, protected_source=lambda _path: False):
        super().__init__(parent)
        self.tr_text = texts
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
        self.xsd.textChanged.connect(self.refresh_buttons)
        self.invalidate()

    def paths(self):
        return (self.master.text().strip(), self.source.text().strip(),
                self.xsd.text().strip() or None)

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

    def invalidate(self, *_args):
        self.panel.invalidate()
        self._refresh_inputs()

    def refresh_buttons(self, *_args):
        self.panel.refresh_buttons()
        self._refresh_inputs()

    def _refresh_inputs(self):
        self.inputs.setEnabled(self.panel.editable)
