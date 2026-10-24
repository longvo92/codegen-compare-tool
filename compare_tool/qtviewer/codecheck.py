"""Independent CURRENT-source check workspace; checker policy stays in consistency.py."""

from pathlib import Path
from pprint import pformat

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFontDatabase, QTextCursor
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar,
                               QPushButton, QSplitter, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import theme
from ..main import _current_consistency_lines
from ..scanner import read_text
from ..syntax import language_for
from .diffpane import DiffEditor
from .highlight import CodeHighlighter
from .worker import CodeCheckWorker


class CodeCheckPage(QWidget):
    """Own inputs/results independently of Compare, including incomplete coverage."""

    def __init__(self, current_source, parent=None):
        super().__init__(parent)
        self._current_source = current_source
        self.worker = None
        self.check = None
        self.root = None
        self._rows = []
        self._status_role = 'state-idle'
        self._run_description = ''

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel('Code Check')
        title.setObjectName('checkTitle')
        header.addWidget(title)
        header.addStretch()
        self.status = QLabel('NOT RUN')
        self.status.setObjectName('checkStatus')
        header.addWidget(self.status)
        layout.addLayout(header)
        subtitle = QLabel('Validate one generated snapshot against its AUTOSAR contract. No baseline required.')
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        workspace = QSplitter(Qt.Horizontal)
        setup = QWidget()
        setup.setMinimumWidth(280)
        form = QVBoxLayout(setup)
        form.setContentsMargins(0, 0, 12, 0)
        form.setSpacing(12)
        self.inputs = QGroupBox('Check setup')
        fields = QVBoxLayout(self.inputs)
        fields.addWidget(QLabel('CURRENT folder or ZIP'))
        self.source = QLineEdit()
        self.source.setPlaceholderText('Select or drop a folder / ZIP')
        self.source.setClearButtonEnabled(True)
        fields.addWidget(self.source)
        browse = QHBoxLayout()
        folder = QPushButton('Folder…')
        folder.clicked.connect(self._pick_folder)
        archive = QPushButton('ZIP…')
        archive.clicked.connect(self._pick_zip)
        browse.addWidget(folder)
        browse.addWidget(archive)
        fields.addLayout(browse)
        self.use_current = QPushButton('Use Compare CURRENT')
        self.use_current.clicked.connect(self._use_current)
        fields.addWidget(self.use_current)
        fields.addWidget(QLabel('Coverage policy'))
        self.policy = QComboBox()
        self.policy.addItem('Delivery — require complete coverage', 'delivery')
        self.policy.addItem('Standard — report coverage gaps', 'standard')
        fields.addWidget(self.policy)
        fields.addWidget(QLabel('Policy config (optional YAML / JSON)'))
        self.config = QLineEdit()
        self.config.setPlaceholderText('Built-in defaults')
        self.config.setClearButtonEnabled(True)
        fields.addWidget(self.config)
        config_browse = QPushButton('Choose config…')
        config_browse.clicked.connect(self._pick_config)
        fields.addWidget(config_browse)
        form.addWidget(self.inputs)

        self.scope = QGroupBox('Scope overrides (optional)')
        scope_form = QFormLayout(self.scope)
        self.excludes = QPlainTextEdit()
        self.excludes.setPlaceholderText('Excluded globs, one per line')
        self.excludes.setMaximumHeight(72)
        self.ignore = QLineEdit()
        self.ignore.setPlaceholderText('Additional ignored-port regex')
        scope_form.addRow('Exclude', self.excludes)
        scope_form.addRow('Ignore ports', self.ignore)
        form.addWidget(self.scope)
        self.run_button = QPushButton('Run Code Check')
        self.run_button.setObjectName('runCodeCheck')
        self.run_button.clicked.connect(self.start_check)
        form.addWidget(self.run_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        form.addWidget(self.progress)
        scope_note = QLabel('Scope: generated .c Rte_Read / Write / IRead / IWrite calls and ARXML '
                            'Sender/Receiver declarations. Other RTE APIs remain UNCHECKED.')
        scope_note.setWordWrap(True)
        form.addWidget(scope_note)
        form.addStretch()
        workspace.addWidget(setup)

        results = QWidget()
        body = QVBoxLayout(results)
        body.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel('Choose a source and run Code Check to see findings and coverage.')
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.PlainText)
        body.addWidget(self.summary)
        self.result_source = QLabel()
        self.result_source.setTextFormat(Qt.PlainText)
        self.result_source.setWordWrap(True)
        self.result_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.result_source)
        self.tabs = QTabWidget()
        findings = QWidget()
        finding_layout = QVBoxLayout(findings)
        finding_layout.setContentsMargins(0, 8, 0, 0)
        filters = QHBoxLayout()
        self.severity = QComboBox()
        self.severity.addItems(['All results', 'FAIL', 'WARN', 'UNCHECKED', 'EXCEPTION'])
        self.severity.currentTextChanged.connect(self._filter_rows)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter by rule, file, runnable or API…')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_rows)
        filters.addWidget(self.severity)
        filters.addWidget(self.search, 1)
        finding_layout.addLayout(filters)
        self.visible_count = QLabel('No results yet')
        finding_layout.addWidget(self.visible_count)
        split = QSplitter(Qt.Vertical)
        self.findings = QTreeWidget()
        self.findings.setHeaderLabels(['Severity', 'Rule', 'File', 'Line', 'Function / Runnable', 'API / Access'])
        self.findings.setRootIsDecorated(False)
        self.findings.setAlternatingRowColors(True)
        self.findings.setUniformRowHeights(True)
        self.findings.header().setSectionResizeMode(QHeaderView.Interactive)
        for col, width in enumerate((100, 235, 210, 55, 180, 200)):
            self.findings.setColumnWidth(col, width)
        self.findings.itemSelectionChanged.connect(self._select_finding)
        split.addWidget(self.findings)
        inspect = QSplitter(Qt.Horizontal)
        self.details = self._text_box('Select a finding to inspect its evidence.')
        source_box = QWidget()
        source_layout = QVBoxLayout(source_box)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_location = QLabel('Source')
        self.source_location.setTextFormat(Qt.PlainText)
        self.source_location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.source_preview = DiffEditor()
        self.source_preview.setPlaceholderText('Source context appears here.')
        self.source_preview.zoomStep.connect(self.source_preview.zoom_by)
        self.source_highlighter = CodeHighlighter(self.source_preview.document())
        source_layout.addWidget(self.source_location)
        source_layout.addWidget(self.source_preview, 1)
        inspect.addWidget(self.details)
        inspect.addWidget(source_box)
        inspect.setSizes([280, 480])
        split.addWidget(inspect)
        split.setSizes([300, 240])
        finding_layout.addWidget(split, 1)
        self.tabs.addTab(findings, 'Findings')
        self.coverage = self._text_box('Coverage and effective policy appear after a check.')
        self.tabs.addTab(self.coverage, 'Coverage & policy')
        body.addWidget(self.tabs, 1)
        workspace.addWidget(results)
        workspace.setStretchFactor(0, 0)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([320, 880])
        layout.addWidget(workspace, 1)

        for edit in (self.source, self.config, self.ignore):
            edit.textChanged.connect(self._inputs_changed)
        self.excludes.textChanged.connect(self._inputs_changed)
        self.policy.currentIndexChanged.connect(self._inputs_changed)
        self.refresh_current()
        self._inputs_changed()
        self.apply_theme()

    @staticmethod
    def _text_box(placeholder):
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        box.setLineWrapMode(QPlainTextEdit.NoWrap)
        box.setPlaceholderText(placeholder)
        return box

    def refresh_current(self):
        self.use_current.setEnabled(bool(self._current_source()))

    def _use_current(self):
        source = self._current_source()
        if source:
            self.source.setText(str(source))

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'CURRENT folder', self.source.text())
        if path:
            self.source.setText(path)

    def _pick_zip(self):
        path, _ = QFileDialog.getOpenFileName(self, 'CURRENT ZIP', '', 'ZIP archives (*.zip);;All files (*)')
        if path:
            self.source.setText(path)

    def _pick_config(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Code Check policy', '',
                                             'Policy files (*.yaml *.yml *.json);;All files (*)')
        if path:
            self.config.setText(path)

    def _inputs_changed(self):
        if self.check is not None:
            self._set_status('STALE — run again', 'state-busy')
        self.run_button.setEnabled(bool(self.source.text().strip()) and not self.is_running())

    def is_running(self):
        return bool(self.worker and self.worker.isRunning())

    def start_check(self):
        if self.is_running() or not self.source.text().strip():
            return
        self.cleanup()
        source = str(Path(self.source.text().strip()).resolve())
        config_path = self.config.text().strip()
        policy = self.policy.currentData()
        exclude = tuple(line.strip() for line in self.excludes.toPlainText().splitlines() if line.strip())
        self._run_description = 'CURRENT: {}\nPolicy: {}\nConfig: {}'.format(
            source, policy, str(Path(config_path).resolve()) if config_path else 'Built-in defaults')
        self.result_source.setText(self._run_description)
        self.check = None
        self.root = None
        self._rows = []
        self.findings.clear()
        self.details.clear()
        self._clear_source()
        self.coverage.clear()
        self.visible_count.setText('Checking…')
        self.summary.setText('Checking CURRENT C and ARXML…')
        self._set_status('RUNNING', 'state-busy')
        self.inputs.setEnabled(False)
        self.scope.setEnabled(False)
        self.run_button.setEnabled(False)
        self.progress.show()
        self.worker = CodeCheckWorker(source, config_path, policy, exclude, self.ignore.text().strip(), self)
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        self.inputs.setEnabled(True)
        self.scope.setEnabled(True)
        self.run_button.setEnabled(bool(self.source.text().strip()))
        self.progress.hide()
        self.refresh_current()

    def _done(self, check, root):
        self.check, self.root = check, Path(root)
        self._set_status(check.status, 'state-error' if check.status in ('FAIL', 'INCOMPLETE') else 'state-ready')
        self.summary.setText('{} FAIL    ·    {} WARN    ·    {} UNCHECKED    ·    '
                             '{} / {} RTE calls checked    ·    {} exceptions'.format(
                                 sum(f['severity'] == 'fail' for f in check.findings),
                                 sum(f['severity'] == 'warn' for f in check.findings),
                                 len(check.skipped_accesses), check.checked_calls,
                                 check.rte_calls_detected, len(check.exemptions)))
        self.coverage.setPlainText(self._run_description + '\n\n' +
                                   '\n'.join(_current_consistency_lines(check)))
        self._rows = [(f['severity'].upper(), f) for f in check.findings]
        self._rows += [('UNCHECKED', f) for f in check.skipped_accesses]
        self._rows += [('EXCEPTION', f) for f in check.exemptions]
        self._filter_rows()

    def _failed(self, message):
        self._set_status('INCOMPLETE', 'state-error')
        self.summary.setText('Code Check could not complete: ' + message)
        self.coverage.setPlainText(self._run_description + '\n\nINCOMPLETE\n' + message)
        self.visible_count.setText('No results — check did not complete')

    @staticmethod
    def _columns(severity, finding):
        call = finding.get('call')
        return [severity, finding['reason'],
                call.file if call else finding.get('file') or finding.get('arxml_file', ''),
                str(call.line) if call else '',
                (call.function or '') if call else finding.get('runnable', ''),
                call.api if call else ' / '.join(str(finding[k]) for k in ('port', 'data_element') if k in finding)]

    def _filter_rows(self):
        self.findings.clear()
        self.details.clear()
        self._clear_source()
        wanted = self.severity.currentText()
        query = self.search.text().casefold().strip()
        for severity, finding in self._rows:
            columns = self._columns(severity, finding)
            if wanted != 'All results' and severity != wanted:
                continue
            if query and query not in (' '.join(columns) + ' ' + pformat(finding)).casefold():
                continue
            item = QTreeWidgetItem(columns)
            item.setData(0, Qt.UserRole, finding)
            for col, value in enumerate(columns):
                item.setToolTip(col, value)
            role = {'FAIL': 'state-error', 'WARN': 'accent',
                    'UNCHECKED': 'state-busy', 'EXCEPTION': 'fg-dim'}[severity]
            item.setForeground(0, QBrush(QColor(theme.c(role))))
            self.findings.addTopLevelItem(item)
        count = self.findings.topLevelItemCount()
        self.visible_count.setText('{} of {} results shown'.format(count, len(self._rows)) if self._rows
                                   else ('No findings or unchecked items.' if self.check else 'No results yet'))
        if count:
            self.findings.setCurrentItem(self.findings.topLevelItem(0))

    def _select_finding(self):
        item = self.findings.currentItem()
        if item is None:
            return
        finding = item.data(0, Qt.UserRole)
        lines = [item.text(0) + ' — ' + finding['reason']]
        for key, value in finding.items():
            if key not in ('call', 'reason', 'severity'):
                lines.append('{}: {}'.format(key.replace('_', ' ').capitalize(),
                                             value if isinstance(value, str) else pformat(value)))
        call = finding.get('call')
        if call:
            lines.extend(['File: {}:{}'.format(call.file, call.line),
                          'Function: {}'.format(call.function or '(unresolved)'), 'API: ' + call.api])
        self.details.setPlainText('\n\n'.join(lines))
        rel = item.text(2)
        if not self.root or not rel or rel == '.':
            self._clear_source('No source location for this result.')
            return
        try:
            path = (self.root / rel).resolve()
            if self.root.resolve() not in path.parents:
                raise ValueError('source location is outside CURRENT')
            source = read_text(path)
            line = call.line if call else 1
            self.source_location.setText('{}:{}'.format(rel, line) if call else rel)
            self.source_location.setToolTip(str(path))
            self.source_highlighter.configure(language_for(rel), repaint=False)
            self.source_preview.setPlainText(source)
            self.source_preview.set_numbers([str(i + 1) for i in range(len(source.splitlines()))])
            self.source_preview.set_current_rows([line - 1] if call else [])
            block = self.source_preview.document().findBlockByNumber(line - 1)
            if block.isValid():
                self.source_preview.setTextCursor(QTextCursor(block))
                self.source_preview.centerCursor()
        except Exception as e:
            self._clear_source('Source could not be read: {}'.format(e))

    def _clear_source(self, message=''):
        self.source_highlighter.configure(None, repaint=False)
        self.source_location.setText('Source')
        self.source_location.setToolTip('')
        self.source_preview.setPlainText(message)
        self.source_preview.set_numbers([])
        self.source_preview.set_current_rows([])

    def _set_status(self, text, role):
        self.status.setText(text)
        self._status_role = role
        self.apply_theme()

    def apply_theme(self):
        self.source_preview.apply_theme()
        self.source_highlighter.apply_theme()
        self.setStyleSheet('QLabel#checkTitle {font-size:24px; font-weight:600;} '
                          'QLabel#checkStatus {color:%s; background:%s; padding:7px 14px; '
                          'border-radius:4px; font-weight:bold;} '
                          'QPushButton#runCodeCheck {background:%s; color:%s; border:1px solid %s; '
                          'border-radius:4px; padding:10px; font-weight:bold;} '
                          'QPushButton#runCodeCheck:disabled {background:%s; color:%s;}' % (
                              theme.c(self._status_role), theme.c('panel-3'),
                              theme.c('chrome-checked-bg'), theme.c('chrome-checked-fg'),
                              theme.c('chrome-checked-bg'),
                              theme.c('panel-3'), theme.c('fg-muted')))
        for i in range(self.findings.topLevelItemCount()):
            item = self.findings.topLevelItem(i)
            role = {'FAIL': 'state-error', 'WARN': 'accent',
                    'UNCHECKED': 'state-busy', 'EXCEPTION': 'fg-dim'}[item.text(0)]
            item.setForeground(0, QBrush(QColor(theme.c(role))))

    def cleanup(self):
        if self.worker and not self.worker.isRunning():
            self.worker.cleanup()
            self.worker.deleteLater()
            self.worker = None
